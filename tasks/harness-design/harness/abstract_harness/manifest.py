"""Final manifest (``submission.json``) and integrity-check capture.

The manifest always describes the *last-good* image: the digest comes from
Docker's resolved image digest, never from a tag or a guess. Values only the
organizer can supply stay as ``UNAVAILABLE_IN_DRAFT: <why>`` strings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import procs

if TYPE_CHECKING:
    from .loop import Harness

STARTER_COMMIT = "81aead87d78ed468c4c374fb42921471b44c3f80"
UNAVAILABLE = "UNAVAILABLE_IN_DRAFT"


def unavailable(why: str) -> str:
    """Literal marker for organizer-only values that do not exist in the draft."""
    return f"{UNAVAILABLE}: {why}"


def run_integrity_check(
    repo_root: Path, base: str, *, timeout_s: float = 300
) -> tuple[int | None, str]:
    """Run the protected integrity checker; return ``(returncode, combined output)``."""
    result = procs.run(
        [sys.executable, "-B", "-m", "tools.check_integrity", "--base", base],
        timeout_s=timeout_s,
        cwd=repo_root,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.timed_out:
        output += "\n[integrity check timed out]"
    return result.returncode, output


def build_manifest(
    harness: Harness, *, integrity_output: str, integrity_rc: int | None
) -> dict[str, Any]:
    """Compose the manifest dict for the harness's current last-good image."""
    cfg = harness.config
    state = harness.state
    example = json.loads(
        (cfg.repo_root / "tasks" / "harness-design" / "submission.example.json").read_text(
            encoding="utf-8"
        )
    )
    engine = harness.engine
    last_good = state.last_good
    image_ref = (
        f"{last_good.tag.split(':')[0]}@{last_good.digest}"
        if last_good
        else unavailable("no image passed the development checks")
    )
    manifest: dict[str, Any] = dict(example)
    manifest["schema_version"] = example.get("schema_version", 2)
    manifest["task"] = "harness-design"
    manifest["status"] = (
        "development-evidence-on-candidate-built-cpu-standin-not-an-official-submission"
        if engine.name == "standin"
        else "candidate-submission-draft"
    )
    manifest["image"] = image_ref
    manifest["platform"] = engine.spec.platform
    manifest["source"] = {
        "repository": "https://github.com/sharonbasovich/performance_takehome",
        "commit": state.source_commit,
        "dockerfile": cfg.rel(engine.spec.dockerfile),
        "build_command": (
            f"docker buildx build --platform {engine.spec.platform} --load "
            f"-f {cfg.rel(engine.spec.dockerfile)} -t candidate "
            f"{cfg.rel(engine.spec.build_context)}"
        ),
        "engine_source_revision": (
            "llama.cpp 620d2225cc436ab0b001e3200e590e3b286ef9ab (v0.7.0)"
            if engine.name == "standin"
            else unavailable(
                "LLMD source is closed; baseline/lock.json engine_source_revision is null"
            )
        ),
        "patches": [last_good.patch] if last_good and last_good.patch else [],
        "provenance_path": cfg.rel(cfg.reports_dir / "build-provenance.json"),
    }
    if engine.name == "standin":
        manifest["model"] = {
            "repository": "unsloth/SmolLM2-135M-Instruct-GGUF",
            "revision": "9e6855bc4be717fca1ef21360a1db4b29d5c559a",
            "note": "CANDIDATE-BUILT CPU stand-in model, not the organizer's pinned snapshot",
        }
    manifest["agent_harness"] = {
        "base_package": "@earendil-works/pi-coding-agent",
        "base_version": "1.0.0",
        "base_profile": "plain-pi-1.0",
        "entrypoint": "tasks/harness-design/harness/run.py",
        "proposer_used": harness.proposer.name,
        "provenance_path": cfg.rel(cfg.reports_dir / "agent-provenance.json"),
    }
    manifest["integrity"] = {
        "starter_commit": STARTER_COMMIT,
        "starter_tag_note": "organizer tag `takehome-start` is absent in the draft; "
        "the starter commit SHA was used instead",
        "command": f"python -B -m tools.check_integrity --base {STARTER_COMMIT}",
        "returncode": integrity_rc,
        "report": cfg.rel(cfg.reports_dir / "integrity.txt"),
    }
    manifest["evaluation"] = {
        "owner": "organizer",
        "mode": "offline-black-box-after-submission",
        "official_result": unavailable("organizer benchmark has not been run"),
    }
    manifest["development_benchmark"] = {
        "owner": "candidate",
        "config": cfg.rel(cfg.benchmark_path),
        "engine": engine.name,
    }
    runtime_args: list[str] = []
    if last_good:
        try:
            from . import docker_runtime as docker

            runtime_args = engine.full_runtime_args(docker.image_cmd(last_good.tag))
        except Exception:  # noqa: BLE001 - manifest must still be written if docker is gone
            runtime_args = list(engine.spec.model_args)
    manifest["runtime"] = {"args": runtime_args, "environment": {}}
    manifest["evidence"] = {
        "experiment_log": cfg.rel(cfg.results_path),
        "report": "tasks/harness-design/NOTES.md",
        "development_reports": [
            cfg.rel(p)
            for p in sorted(cfg.reports_dir.glob("*.json"))
            if p.name
            not in {"build-provenance.json", "agent-provenance.json", "final-manifest.json"}
        ],
        "agent_transcripts": [],
        "last_good": {
            "tag": last_good.tag if last_good else "",
            "digest": last_good.digest if last_good else "",
            "experiment": last_good.experiment if last_good else "",
            "development_report": last_good.report if last_good else "",
        },
        "finish_reason": state.finish_reason,
        "api_usd_cumulative": round(state.api_usd_cumulative, 4),
    }
    return manifest


def write_manifest(harness: Harness) -> dict[str, Any]:
    """Run the integrity check, write provenance/integrity files and the ``--out`` manifest."""
    cfg = harness.config
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    rc, output = run_integrity_check(cfg.repo_root, STARTER_COMMIT)
    (cfg.reports_dir / "integrity.txt").write_text(
        f"$ python -B -m tools.check_integrity --base {STARTER_COMMIT}\n"
        f"{output}\n[exit code {rc}]\n",
        encoding="utf-8",
    )
    manifest = build_manifest(harness, integrity_output=output, integrity_rc=rc)
    state = harness.state
    provenance = {
        "engine": harness.engine.name,
        "build_context": cfg.rel(harness.engine.spec.build_context),
        "dockerfile": cfg.rel(harness.engine.spec.dockerfile),
        "base_image": harness.engine.spec.base_image,
        "last_good": state.last_good.__dict__ if state.last_good else None,
        "attempts": len(state.history),
        "source_commit": state.source_commit,
        "digest_resolution": "docker buildx --metadata-file containerimage.digest / "
        "docker image inspect RepoDigests",
    }
    (cfg.reports_dir / "build-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    agent = {
        "proposer": harness.proposer.name,
        "pi_package": "@earendil-works/pi-coding-agent",
        "pi_version": "1.0.0",
        "pi_integrity": "sha512-/FtbxoSQU/mEv1QnichJjRjqteqaIaMWxmhB4G367+MwZfX7/"
        "DI5B9YAg5lqbN7nztFskBEtUSZ+FlmMBECtMw==",
        "pi_used_for_these_rows": harness.proposer.name == "pi",
        "api_usd_cumulative": round(state.api_usd_cumulative, 4),
        "note": "ScriptedProposer rows involve no coding-model calls; "
        "API spend is 0 by construction."
        if harness.proposer.name != "pi"
        else "",
    }
    (cfg.reports_dir / "agent-provenance.json").write_text(
        json.dumps(agent, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    cfg.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    cfg.out_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
