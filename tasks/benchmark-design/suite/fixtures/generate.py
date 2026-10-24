"""Generate the public (labeled) and held-out (opaque) event fixtures on the CPU mock.

    cd tasks/benchmark-design/suite && python fixtures/generate.py [--time-scale 0.25] [--only NAME]

For every mock profile the runner cold-starts a mock server via ``--launch-cmd`` (so the
startup axis has real launch evidence), runs ``workload.mock.json`` in ``fixture`` mode and
stores ``run.json`` + ``requests.jsonl.gz`` + the mock's ``oracle.json`` + ``label.json``.
Two families that no server can produce (invalid timing, client lag) are derived from the
clean capture by mutating the recorded evidence. Held-out fixtures reuse a subset of
profiles with fresh seeds under opaque directory names; the key is written to
``validation/heldout_key.json`` and is never read by ``evaluate.py``.
"""

import argparse
import gzip
import hashlib
import json
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SUITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUITE))

from mock_server.faults import PROFILES  # noqa: E402

FIXTURE_DIR = SUITE / "fixtures"
PUBLIC_DIR = FIXTURE_DIR / "public"
HELDOUT_DIR = FIXTURE_DIR / "heldout"
KEY_PATH = SUITE.parent / "validation" / "heldout_key.json"
MOCK_PLAN = FIXTURE_DIR / "workload.mock.json"
MUTATIONS = {
    "timing_invalid": "events in 10% of measured requests re-ordered: non-monotonic timestamps",
    "client_lag": "run.json client_integrity reports a 0.4 s event-loop stall in a measure window",
}
HELDOUT_PROFILES = (
    "clean",
    "noisy",
    "stall",
    "burst",
    "missing_done",
    "wrong_text",
    "false_usage",
    "drop",
    "late_first_token",
    "truncated_text",
)

# What the evaluator is expected to conclude; checked by validation/build_validation.py and
# the tests. "signal" names the gate/metric that must carry the detection.
EXPECTED: dict[str, dict[str, Any]] = {
    "clean": {"status": "valid", "signal": "none (control)"},
    "noisy": {
        "status": "valid",
        "signal": "none (control); A/A must stay no_difference/inconclusive",
    },
    "burst": {
        "status": "valid",
        "signal": "token_evidence.multi_token_deltas flag; strict fluidity index drops",
    },
    "stall": {
        "status": "valid",
        "signal": "fluidity index drops at every tier; min decode deadline p99 rises",
    },
    "late_first_token": {
        "status": "valid",
        "signal": "TTFT p50 rises; prefill_deadline_hit_rate falls",
    },
    "slow_decode": {
        "status": "valid",
        "signal": "strict fluidity SLO fails; MDD p99 rises; FTGR falls",
    },
    "reasoning_channel": {
        "status": "valid",
        "signal": "reasoning tokens counted separately; TTFT = first content token",
    },
    "unicode_split": {
        "status": "valid",
        "signal": "tokens counted once across split deltas; no replacement chars",
    },
    "missing_done": {"status": "valid", "signal": "gate missing_done -> unfinished"},
    "missing_finish_reason": {
        "status": "valid",
        "signal": "gate missing_finish_reason -> unfinished",
    },
    "http_error": {"status": "valid", "signal": "gate http_error -> failed"},
    "drop": {"status": "valid", "signal": "gate drop/missing_done -> unfinished"},
    "wrong_text": {"status": "valid", "signal": "gate invalid_output (nonce/sequence) -> failed"},
    "garbled_text": {
        "status": "valid",
        "signal": "gate invalid_output (replacement/garbled) -> failed",
    },
    "truncated_text": {
        "status": "valid",
        "signal": "gate invalid_output (too short / sequence) -> failed",
    },
    "false_usage": {"status": "valid", "signal": "gate usage_discrepancy -> failed"},
    "misleading_readiness": {
        "status": "valid",
        "signal": "startup.readiness_lead_s > 0: ready probe long before first valid generation",
    },
    "slow_startup": {
        "status": "valid",
        "signal": "startup_to_first_valid_generation_s > readiness",
    },
    "timing_invalid": {
        "status": "invalid",
        "signal": "gate invalid_timing -> evidence_invalid -> run invalid",
    },
    "client_lag": {
        "status": "invalid",
        "signal": "run gate: event_loop_lag_max_s > max -> run invalid",
    },
}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_fixture(
    profile: str, seed: int, out: Path, time_scale: float, *, keep_oracle: bool
) -> dict[str, Any]:
    """Cold-start a mock server through the runner and capture one events directory."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    port = free_port()
    oracle_path = out / "oracle.json"
    launch = (
        f"{sys.executable} -m mock_server --profile {profile} --seed {seed} --port {port} "
        f"--time-scale {time_scale} --oracle-dump {oracle_path}"
    )
    cmd = [
        sys.executable,
        "-m",
        "runner",
        "--plan",
        str(MOCK_PLAN),
        "--mode",
        "fixture",
        "--out",
        str(out),
        "--base-url",
        f"http://127.0.0.1:{port}",
        "--time-scale",
        str(time_scale),
        "--assume-mock",
        "--launch-cmd",
        launch,
        "--stop-after-launch",
        "--run-id",
        f"fixture-{profile}-{seed}",
    ]
    started = time.monotonic()
    result = subprocess.run(cmd, cwd=SUITE, capture_output=True, text=True, check=False)
    wall = time.monotonic() - started
    if result.returncode not in (0, 1):
        raise RuntimeError(f"runner failed for {profile}: {result.stderr[-2000:]}")
    for _ in range(50):
        if oracle_path.exists():
            break
        time.sleep(0.1)
    raw = out / "requests.jsonl"
    with raw.open("rb") as src, gzip.open(out / "requests.jsonl.gz", "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    raw.unlink()
    if oracle_path.exists():
        if keep_oracle:
            with (
                oracle_path.open("rb") as src,
                gzip.open(out / "oracle.json.gz", "wb", compresslevel=9) as dst,
            ):
                shutil.copyfileobj(src, dst)
        oracle_path.unlink()
    return {
        "profile": profile,
        "seed": seed,
        "runner_exit": result.returncode,
        "wall_s_cpu_mock": round(wall, 2),
    }


def mutate(clean_dir: Path, mutation: str, out: Path, seed: int) -> None:
    """Derive an evidence-corruption fixture from the clean capture."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    run = json.loads((clean_dir / "run.json").read_text(encoding="utf-8"))
    run["run_id"] = f"fixture-{mutation}-{seed}"
    with gzip.open(clean_dir / "requests.jsonl.gz", "rt", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    rng = random.Random(seed)
    for record in records:
        record["run_id"] = run["run_id"]
    if mutation == "timing_invalid":
        measured = [r for r in records if r["phase"] == "measure" and len(r["events"]) > 4]
        for record in rng.sample(measured, max(1, len(measured) // 10)):
            i = rng.randrange(1, len(record["events"]) - 1)
            record["events"][i]["t"], record["events"][i + 1]["t"] = (
                record["events"][i + 1]["t"],
                record["events"][i]["t"],
            )
    elif mutation == "client_lag":
        window = next(p for p in run["phases"] if p["name"] == "measure")
        ci = run["client_integrity"]
        ci["event_loop_lag_max_s"] = 0.4
        ci["event_loop_lag_max_at_mono_s"] = (window["start"] + window["end"]) / 2
        ci.setdefault("event_loop_lag_spikes", []).append(
            {"t": ci["event_loop_lag_max_at_mono_s"], "lag_s": 0.4}
        )
    else:
        raise ValueError(mutation)
    (out / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    with gzip.open(out / "requests.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def opaque_name(profile: str, seed: int, salt: str) -> str:
    return "hx-" + hashlib.sha256(f"{salt}|{profile}|{seed}".encode()).hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--time-scale", type=float, default=0.25)
    parser.add_argument("--only", help="generate only this profile/mutation (public set)")
    parser.add_argument("--skip-heldout", action="store_true")
    parser.add_argument("--heldout-salt", default="abstract-t1-heldout-v1")
    args = parser.parse_args(argv)
    manifest: dict[str, Any] = {
        "time_scale": args.time_scale,
        "public": {},
        "heldout_count": 0,
        "note": "CPU mock fixtures; injected timings, not GPU measurements.",
    }
    for index, profile in enumerate(PROFILES):
        if args.only and args.only != profile:
            continue
        seed = 100 + index
        out = PUBLIC_DIR / profile
        info = run_fixture(profile, seed, out, args.time_scale, keep_oracle=True)
        label = {
            **info,
            "family": PROFILES[profile].family,
            "description": PROFILES[profile].description,
            "expected": EXPECTED[profile],
        }
        (out / "label.json").write_text(json.dumps(label, indent=2), encoding="utf-8")
        manifest["public"][profile] = info
        print(json.dumps(info), flush=True)
    clean_dir = PUBLIC_DIR / "clean"
    for index, (mutation, description) in enumerate(MUTATIONS.items()):
        if args.only and args.only != mutation:
            continue
        out = PUBLIC_DIR / mutation
        mutate(clean_dir, mutation, out, 900 + index)
        label = {
            "profile": mutation,
            "seed": 900 + index,
            "family": "evidence_corruption",
            "derived_from": "clean",
            "description": description,
            "expected": EXPECTED[mutation],
        }
        (out / "label.json").write_text(json.dumps(label, indent=2), encoding="utf-8")
        manifest["public"][mutation] = {"derived_from": "clean"}
        print(json.dumps({"mutation": mutation}), flush=True)
    if not args.skip_heldout and not args.only:
        if HELDOUT_DIR.exists():
            shutil.rmtree(HELDOUT_DIR)
        key: dict[str, Any] = {}
        for index, profile in enumerate(HELDOUT_PROFILES):
            seed = 500 + index
            name = opaque_name(profile, seed, args.heldout_salt)
            with tempfile.TemporaryDirectory() as tmp:
                info = run_fixture(
                    profile, seed, Path(tmp) / name, args.time_scale, keep_oracle=False
                )
                shutil.copytree(Path(tmp) / name, HELDOUT_DIR / name)
            key[name] = {**info, "family": PROFILES[profile].family, "expected": EXPECTED[profile]}
            print(
                json.dumps({"heldout": name, "wall_s_cpu_mock": info["wall_s_cpu_mock"]}),
                flush=True,
            )
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        KEY_PATH.write_text(json.dumps(key, indent=2), encoding="utf-8")
        manifest["heldout_count"] = len(key)
    (FIXTURE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
