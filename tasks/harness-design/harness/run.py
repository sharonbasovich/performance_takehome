"""Entrypoint for the Task 2 candidate harness.

Example (CPU stand-in, scripted proposer, no API key needed):

    uv run --frozen python tasks/harness-design/harness/run.py run \
        --engine standin --model-dir /path/to/standin-model \
        --experiments tasks/harness-design/harness/experiments/standin-queue.json \
        --state-dir /tmp/harness-state --budget-minutes 120 --api-spend-limit-usd 0 \
        --out /tmp/harness-state/submission.json \
        --results tasks/harness-design/harness/results.tsv

Example (real target, MI355X + coding-model key):

    PI_BIN=/path/to/node_modules/.bin/pi ANTHROPIC_API_KEY=... \
    uv run --frozen python tasks/harness-design/harness/run.py run \
        --engine llmd --model-dir /models/Qwen3.6-27B --proposer pi \
        --api-key-env ANTHROPIC_API_KEY \
        --baseline baseline/lock.json --budget-minutes 360 --api-spend-limit-usd 200 \
        --gpu-hours 64 --out tasks/harness-design/submission.json \
        --results tasks/harness-design/harness/results.tsv

Re-running the same command with the same ``--state-dir`` resumes from disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from abstract_harness import budget as budget_mod  # noqa: E402
from abstract_harness import results as results_mod  # noqa: E402
from abstract_harness.engines import make_engine  # noqa: E402
from abstract_harness.loop import Harness, LoopConfig, Timeouts  # noqa: E402
from abstract_harness.proposers import PiLaunchConfig, PiProposer, ScriptedProposer  # noqa: E402
from abstract_harness.state import StateError  # noqa: E402

STANDIN_MODEL = {
    "repo": "unsloth/SmolLM2-135M-Instruct-GGUF",
    "revision": "9e6855bc4be717fca1ef21360a1db4b29d5c559a",
    "filename": "SmolLM2-135M-Instruct-Q8_0.gguf",
    "sha256": "c4a3dd037301b6ecea31d6da37f5cd793ead920dd5ddfe6d589294628d6ce66a",
    "size": 144811072,
}


def _git_head(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    """CLI definition."""
    parser = argparse.ArgumentParser(
        prog="run.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run (or resume) the optimization loop")
    run.add_argument("--engine", choices=["llmd", "standin"], required=True)
    run.add_argument(
        "--model-dir", type=Path, required=True, help="directory mounted read-only at /models/model"
    )
    run.add_argument(
        "--baseline",
        type=Path,
        default=REPO_ROOT / "baseline" / "lock.json",
        help="pinned LLMD lock (llmd engine)",
    )
    run.add_argument(
        "--development-benchmark", type=Path, default=HERE / "development-benchmark.json"
    )
    run.add_argument("--program", type=Path, default=HERE / "program.md")
    run.add_argument("--results", type=Path, default=HERE / "results.tsv")
    run.add_argument("--out", type=Path, required=True, help="manifest path (submission.json)")
    run.add_argument(
        "--state-dir", type=Path, required=True, help="persistent state (resume) + scratch + logs"
    )
    run.add_argument("--reports-dir", type=Path, default=HERE / "reports")
    run.add_argument("--patches-dir", type=Path, default=HERE / "patches")
    run.add_argument("--proposer", choices=["scripted", "pi"], default="scripted")
    run.add_argument("--experiments", type=Path, help="scripted proposer queue (JSON)")
    run.add_argument(
        "--api-key-env",
        default="ANTHROPIC_API_KEY",
        help="env var holding the coding-model key (value never logged)",
    )
    run.add_argument("--pi-bin", type=Path, default=Path(os.environ.get("PI_BIN", "pi")))
    run.add_argument("--pi-model", default=None)
    run.add_argument("--pi-provider", default=None)
    run.add_argument(
        "--pi-usd-per-call",
        type=float,
        default=0.0,
        help="ledger estimate per Pi call when Pi emits no cost",
    )
    run.add_argument("--budget-minutes", type=float, required=True, help="lease length from now")
    run.add_argument("--final-reserve-minutes", type=float, default=15.0)
    run.add_argument("--api-spend-limit-usd", type=float, required=True)
    run.add_argument(
        "--gpu-hours",
        type=float,
        default=64.0,
        help="GPU-hour allocation (allocation x elapsed accounting)",
    )
    run.add_argument("--gpus", type=int, default=1, help="GPUs allocated (0 for the CPU stand-in)")
    run.add_argument("--max-attempts", type=int, default=None)
    run.add_argument("--estimated-attempt-minutes", type=float, default=10.0)
    run.add_argument("--build-timeout-s", type=float, default=1800.0)
    run.add_argument("--startup-timeout-s", type=float, default=300.0)
    run.add_argument("--measure-timeout-s", type=float, default=900.0)
    run.add_argument("--min-effect", type=float, default=0.03)
    run.add_argument("--min-samples", type=int, default=3)
    run.add_argument("--render-device", default="/dev/dri/renderD128")
    run.add_argument("--render-gid", default=None)
    run.add_argument("--standin-cpus", default="4")
    run.add_argument(
        "--no-cache",
        action="store_true",
        help="pass --no-cache to every docker build in this invocation (cold rebuild)",
    )
    run.add_argument("--keep-candidate-images", action="store_true")

    val = sub.add_parser("validate-results", help="validate a results.tsv against the contract")
    val.add_argument("--results", type=Path, default=HERE / "results.tsv")

    fetch = sub.add_parser(
        "fetch-standin-model", help="download + verify the pinned stand-in GGUF (network required)"
    )
    fetch.add_argument("--dest", type=Path, required=True)

    retag = sub.add_parser(
        "retag-last-good", help="tag the last-good image recorded in a state dir"
    )
    retag.add_argument("--state-dir", type=Path, required=True)
    retag.add_argument("--tag", required=True)
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    """Build config objects and run the loop."""
    now = time.time()
    budget = budget_mod.BudgetConfig(
        api_usd_limit=args.api_spend_limit_usd,
        gpu_hours_limit=args.gpu_hours,
        gpus_allocated=args.gpus,
        lease_start_ts=now,
        lease_deadline_ts=now + args.budget_minutes * 60,
        final_reserve_s=args.final_reserve_minutes * 60,
    )
    engine_kwargs = (
        {
            "render_device": args.render_device,
            "render_gid": args.render_gid,
            "lock_path": args.baseline,
        }
        if args.engine == "llmd"
        else {"cpus": args.standin_cpus}
    )
    engine = make_engine(args.engine, REPO_ROOT, args.model_dir, **engine_kwargs)
    profile = json.loads(
        (REPO_ROOT / "agent-harness" / "profiles.json").read_text(encoding="utf-8")
    )["profiles"]["harness-design"]
    if args.proposer == "pi":
        pi_cfg = PiLaunchConfig(
            pi_bin=args.pi_bin,
            agent_dir=args.state_dir / "pi-agent-dir",
            api_key_env=args.api_key_env,
            model=args.pi_model,
            provider=args.pi_provider,
            usd_per_call_estimate=args.pi_usd_per_call,
        )
        proposer = PiProposer(pi_cfg, profile=profile)
        if not proposer.api_key_present():
            print(
                f"[run] {args.api_key_env} is not set; falling back to the scripted proposer",
                file=sys.stderr,
            )
            if not args.experiments:
                print("[run] no --experiments queue given for the fallback", file=sys.stderr)
                return 2
            proposer = ScriptedProposer.from_file(args.experiments)
        else:
            print(f"[run] pi distribution: {proposer.verify_distribution()}")
    else:
        if not args.experiments:
            print("[run] --experiments is required for the scripted proposer", file=sys.stderr)
            return 2
        proposer = ScriptedProposer.from_file(args.experiments)
    config = LoopConfig(
        repo_root=REPO_ROOT,
        state_dir=args.state_dir,
        results_path=args.results,
        reports_dir=args.reports_dir,
        patches_dir=args.patches_dir,
        benchmark_path=args.development_benchmark,
        program_path=args.program,
        out_manifest=args.out,
        source_commit=_git_head(REPO_ROOT),
        budget=budget,
        timeouts=Timeouts(
            build_s=args.build_timeout_s,
            startup_s=args.startup_timeout_s,
            measure_s=args.measure_timeout_s,
        ),
        max_attempts=args.max_attempts,
        min_effect=args.min_effect,
        no_cache=args.no_cache,
        min_samples=args.min_samples,
        estimated_attempt_s=args.estimated_attempt_minutes * 60,
        keep_candidate_images=args.keep_candidate_images,
    )
    # A scripted proposer resumes at the on-disk attempt index so queue entries are not replayed.
    try:
        harness = Harness(config, engine, proposer)
    except StateError as exc:
        print(f"[run] {exc}", file=sys.stderr)
        return 4
    if isinstance(proposer, ScriptedProposer) and harness.state.attempt_index > 1:
        proposer = ScriptedProposer.from_file(
            args.experiments, skip=harness.state.attempt_index - 1
        )
        harness.proposer = proposer
    return harness.run()


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate ``results.tsv``; print a per-outcome summary."""
    rows = results_mod.validate_file(args.results)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.outcome] = counts.get(row.outcome, 0) + 1
    print(f"{args.results}: {len(rows)} rows OK; outcomes={json.dumps(counts, sort_keys=True)}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download the pinned stand-in model with huggingface_hub and verify its SHA-256."""
    from huggingface_hub import hf_hub_download  # root dependency

    args.dest.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        STANDIN_MODEL["repo"],
        STANDIN_MODEL["filename"],
        revision=STANDIN_MODEL["revision"],
        local_dir=args.dest,
    )
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != STANDIN_MODEL["sha256"]:
        print(f"[fetch] SHA-256 mismatch: {digest}", file=sys.stderr)
        return 1
    target = args.dest / "model.gguf"
    if Path(path).resolve() != target.resolve():
        Path(path).replace(target)
    print(f"[fetch] {target} sha256={digest} size={target.stat().st_size}")
    return 0


def cmd_retag(args: argparse.Namespace) -> int:
    """Retag the last-good image from an existing state file."""
    from abstract_harness import docker_runtime as docker
    from abstract_harness.state import load_state

    state = load_state(args.state_dir / "state.json")
    if state is None or state.last_good is None:
        print("[retag] no last-good image recorded", file=sys.stderr)
        return 1
    source = (
        state.last_good.tag
        if docker.image_exists(state.last_good.tag)
        else state.last_good.image_id or ""
    )
    if not source:
        print("[retag] last-good image is no longer present locally", file=sys.stderr)
        return 1
    docker.retag(source, args.tag)
    print(f"[retag] {source} -> {args.tag} ({state.last_good.digest})")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    args = build_parser().parse_args(argv)
    return {
        "run": cmd_run,
        "validate-results": cmd_validate,
        "fetch-standin-model": cmd_fetch,
        "retag-last-good": cmd_retag,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
