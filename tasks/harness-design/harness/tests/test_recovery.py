"""SIGTERM mid-attempt kills children; a restart logs ``interrupted`` from on-disk state."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from abstract_harness import loop as loop_mod
from abstract_harness import results
from abstract_harness.budget import BudgetConfig
from abstract_harness.proposers import ScriptedProposer
from abstract_harness.state import HarnessState, InProgress, load_state, save_state

from . import _paths


class _FakeEngine:
    name = "standin"


def make_harness(root: Path) -> loop_mod.Harness:
    """A Harness wired to temp paths; nothing here touches Docker."""
    cfg = loop_mod.LoopConfig(
        repo_root=_paths.REPO_ROOT,
        state_dir=root / "state",
        results_path=root / "results.tsv",
        reports_dir=root / "reports",
        patches_dir=root / "patches",
        benchmark_path=_paths.HARNESS_DIR / "development-benchmark.json",
        program_path=_paths.HARNESS_DIR / "program.md",
        out_manifest=root / "manifest.json",
        source_commit="81aead87d78ed468c4c374fb42921471b44c3f80",
        budget=BudgetConfig(
            api_usd_limit=0.0,
            gpu_hours_limit=1.0,
            gpus_allocated=0,
            lease_start_ts=0.0,
            lease_deadline_ts=10**12,
            final_reserve_s=0,
        ),
    )
    return loop_mod.Harness(cfg, _FakeEngine(), ScriptedProposer([]), log=lambda _m: None)


def _seed_in_progress(root: Path, stage: str) -> None:
    state = HarnessState(
        engine="standin",
        source_commit="81aead87d78ed468c4c374fb42921471b44c3f80",
        lease_start_ts=0.0,
    )
    state.in_progress = InProgress(
        experiment="003-hung",
        hypothesis="h",
        started_ts=1.0,
        patch_path="patches/003.patch",
        stage=stage,
    )
    (root / "state").mkdir(parents=True, exist_ok=True)
    save_state(root / "state" / "state.json", state)
    results.ensure_header(root / "results.tsv")
    results.append_row(
        root / "results.tsv",
        results.make_row(
            ts="2026-01-01T00:00:00Z",
            experiment="baseline",
            source_commit=state.source_commit,
            image_digest="sha256:" + "b" * 64,
            kept="1",
            outcome="baseline",
            development_report="reports/baseline.json",
        ),
    )


class RecoverFromDiskTest(unittest.TestCase):
    def test_in_progress_attempt_is_logged_as_interrupted_on_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_in_progress(root, "measuring")
            with (
                mock.patch.object(loop_mod.docker, "kill_containers_with_prefix") as kill,
                mock.patch.object(loop_mod.docker, "remove_image"),
            ):
                harness = make_harness(root)
                harness.recover_from_previous_run()
            kill.assert_called_once()
            rows = results.validate_file(root / "results.tsv")
            self.assertEqual([r.outcome for r in rows], ["baseline", "interrupted"])
            self.assertEqual(rows[1].kept, "0")
            self.assertEqual(rows[1].image_digest, "")
            self.assertEqual(rows[1].local_ttft_speedup, "")
            report = json.loads((root / rows[1].development_report).read_text())
            self.assertEqual(report["stage"], "measuring")
            state = load_state(root / "state" / "state.json")
            assert state is not None
            self.assertIsNone(state.in_progress)
            self.assertEqual(state.attempt_index, 1)

    def test_clean_state_needs_no_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(loop_mod.docker, "kill_containers_with_prefix") as kill:
                make_harness(root).recover_from_previous_run()
            kill.assert_not_called()
            self.assertEqual(results.validate_file(root / "results.tsv"), [])


CHILD = textwrap.dedent(
    """
    import sys, signal
    from pathlib import Path
    sys.path[:0] = [{harness_dir!r}, {repo_root!r}, {tests_parent!r}]
    from tests.test_recovery import make_harness, _seed_in_progress
    from abstract_harness import procs
    from abstract_harness.loop import Interrupted
    root = Path({root!r})
    _seed_in_progress(root, "building")
    h = make_harness(root)
    h.install_signal_handlers()
    (root / "ready").write_text("1")
    try:
        procs.run(["bash", "-c", "sleep 120 & echo $! > {pidfile}; wait"], timeout_s=300)
        sys.exit(99)
    except Interrupted as exc:
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN
        (root / "interrupted").write_text(str(exc))
        sys.exit(3)
    """
)


class SigtermSubprocessTest(unittest.TestCase):
    def test_sigterm_kills_process_group_and_restart_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pidfile = root / "sleep.pid"
            script = CHILD.format(
                harness_dir=str(_paths.HARNESS_DIR),
                repo_root=str(_paths.REPO_ROOT),
                tests_parent=str(_paths.HARNESS_DIR),
                root=str(root),
                pidfile=str(pidfile),
            )
            proc = subprocess.Popen(
                [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            deadline = time.monotonic() + 30
            while not pidfile.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(pidfile.exists(), "child never started its sleep")
            time.sleep(0.2)
            proc.send_signal(signal.SIGTERM)
            _out, err = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 3, err.decode()[-800:])
            self.assertEqual((root / "interrupted").read_text(), "SIGTERM")
            sleep_pid = int(pidfile.read_text().strip())
            time.sleep(0.3)
            with self.assertRaises(ProcessLookupError):
                os.kill(sleep_pid, 0)
            with (
                mock.patch.object(loop_mod.docker, "kill_containers_with_prefix"),
                mock.patch.object(loop_mod.docker, "remove_image"),
            ):
                make_harness(root).recover_from_previous_run()
            rows = results.validate_file(root / "results.tsv")
            self.assertEqual(
                [(r.experiment, r.outcome) for r in rows],
                [("baseline", "baseline"), ("003-hung", "interrupted")],
            )


if __name__ == "__main__":
    unittest.main()
