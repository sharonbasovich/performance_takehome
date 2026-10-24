"""source_commit must name the code that produced a row: HEAD + dirty flag + tree hash."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run

from . import _paths


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


class ProvenanceTest(unittest.TestCase):
    def test_tree_hash_is_deterministic_and_content_sensitive(self) -> None:
        task_dir = _paths.HARNESS_DIR.parent
        first = run.harness_tree_sha256(task_dir)
        self.assertEqual(first, run.harness_tree_sha256(task_dir))
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / "harness").mkdir()
            (fake / "harness" / "run.py").write_text("a", encoding="utf-8")
            before = run.harness_tree_sha256(fake)
            (fake / "harness" / "run.py").write_text("b", encoding="utf-8")
            self.assertNotEqual(before, run.harness_tree_sha256(fake))

    def test_dirty_detection_ignores_evidence_outputs_but_not_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init", "-q")
            code = repo / "tasks" / "harness-design" / "harness"
            code.mkdir(parents=True)
            (code / "run.py").write_text("x", encoding="utf-8")
            _git(repo, "add", ".")
            _git(repo, "commit", "-q", "-m", "init")
            head, dirty = run._git_describe(repo)
            self.assertEqual(head, _git(repo, "rev-parse", "HEAD"))
            self.assertFalse(dirty)
            (code / "results.tsv").write_text("ts\n", encoding="utf-8")
            (code / "reports").mkdir()
            (code / "reports" / "001.json").write_text("{}", encoding="utf-8")
            self.assertFalse(run._git_describe(repo)[1], "evidence outputs are not code")
            (code / "run.py").write_text("changed", encoding="utf-8")
            self.assertTrue(run._git_describe(repo)[1], "edited code is dirty")

    def test_run_refuses_dirty_tree_without_allow_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(run, "_git_describe", return_value=("abc", True)):
                code = run.cmd_run(
                    run.build_parser().parse_args(
                        [
                            "run",
                            "--engine",
                            "standin",
                            "--model-dir",
                            str(root),
                            "--experiments",
                            str(_paths.HARNESS_DIR / "experiments" / "standin-queue.json"),
                            "--state-dir",
                            str(root / "state"),
                            "--out",
                            str(root / "out.json"),
                            "--results",
                            str(root / "results.tsv"),
                            "--gpus",
                            "0",
                            "--budget-minutes",
                            "120",
                            "--api-spend-limit-usd",
                            "0",
                        ]
                    )
                )
            self.assertEqual(code, 2)
            self.assertFalse((root / "results.tsv").exists())
