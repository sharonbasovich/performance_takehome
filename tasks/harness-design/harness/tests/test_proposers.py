"""Proposer contract: scripted queue, patch application, Pi isolation and offline behaviour."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from abstract_harness import proposers
from abstract_harness.proposers import (
    PI_ISOLATION_FLAGS,
    PI_PACKAGE,
    PI_STOCK_TOOLS,
    PI_VERSION,
    PiLaunchConfig,
    PiProposer,
    ProposerContext,
    ProposerError,
    ScriptedProposer,
    apply_patch,
)

from . import _paths

PROFILES = json.loads((_paths.REPO_ROOT / "agent-harness" / "profiles.json").read_text("utf-8"))


def _context(context_dir: Path, work_dir: Path) -> ProposerContext:
    return ProposerContext(
        program_md="# program",
        profile={"name": "test"},
        history=[],
        context_dir=context_dir,
        work_dir=work_dir,
        engine="standin",
    )


class ScriptedProposerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ctx_dir = self.root / "context"
        self.ctx_dir.mkdir()
        (self.ctx_dir / "Dockerfile").write_text("ARG THREADS=4\nFROM scratch\n", encoding="utf-8")
        self.work = self.root / "work"
        self.work.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_queue_yields_real_unified_diffs_in_order_then_none(self) -> None:
        queue = [
            {
                "experiment": "threads-8",
                "hypothesis": "more threads",
                "edits": [{"file": "Dockerfile", "find": "THREADS=4", "replace": "THREADS=8"}],
            },
            {
                "experiment": "threads-any",
                "hypothesis": "regex",
                "edits": [
                    {
                        "file": "Dockerfile",
                        "regex": True,
                        "find": r"THREADS=\d+",
                        "replace": "THREADS=1",
                    }
                ],
            },
        ]
        proposer = ScriptedProposer(queue)
        ctx = _context(self.ctx_dir, self.work)
        first = proposer.propose(ctx)
        assert first is not None
        self.assertIn("threads-8", first.experiment)
        self.assertIn("-ARG THREADS=4", first.patch)
        self.assertIn("+ARG THREADS=8", first.patch)
        ok, _ = apply_patch(first.patch, self.ctx_dir)
        self.assertTrue(ok)
        self.assertIn("THREADS=8", (self.ctx_dir / "Dockerfile").read_text())
        second = proposer.propose(ctx)
        assert second is not None
        self.assertIn("+ARG THREADS=1", second.patch)
        self.assertIsNone(proposer.propose(ctx))

    def test_edit_that_does_not_match_raises(self) -> None:
        proposer = ScriptedProposer(
            [
                {
                    "experiment": "x",
                    "hypothesis": "h",
                    "edits": [{"file": "Dockerfile", "find": "NOPE", "replace": "y"}],
                }
            ]
        )
        with self.assertRaises(ProposerError):
            proposer.propose(_context(self.ctx_dir, self.work))

    def test_edit_outside_context_is_rejected(self) -> None:
        proposer = ScriptedProposer(
            [
                {
                    "experiment": "x",
                    "hypothesis": "h",
                    "edits": [{"file": "../escape", "find": "a", "replace": "b"}],
                }
            ]
        )
        with self.assertRaises(ProposerError):
            proposer.propose(_context(self.ctx_dir, self.work))

    def test_skip_resumes_queue_position(self) -> None:
        queue = [
            {
                "experiment": f"e{i}",
                "hypothesis": "h",
                "edits": [{"file": "Dockerfile", "find": "FROM", "replace": "FROM"}],
            }
            for i in range(3)
        ]
        self.assertEqual(ScriptedProposer(queue, skip=2).remaining, 1)

    def test_apply_patch_rejects_garbage_and_traversal(self) -> None:
        ok, out = apply_patch("this is not a patch", self.ctx_dir)
        self.assertFalse(ok)
        traversal = "--- a/../evil\n+++ b/../evil\n@@ -0,0 +1 @@\n+pwned\n"
        ok, _ = apply_patch(traversal, self.ctx_dir)
        self.assertFalse(ok)
        self.assertFalse((self.root / "evil").exists())


class PiProposerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = PiLaunchConfig(
            pi_bin=root / "pi", agent_dir=root / "agent", api_key_env="HARNESS_TEST_KEY"
        )
        self.profile = PROFILES["profiles"]["harness-design"]
        self.proposer = PiProposer(self.cfg, profile=self.profile)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_pin_matches_profiles_json(self) -> None:
        self.assertEqual(PROFILES["pi"]["package"], PI_PACKAGE)
        self.assertEqual(PROFILES["pi"]["version"], PI_VERSION)
        self.assertEqual(tuple(self.profile["stock_tools"]), PI_STOCK_TOOLS)
        self.assertFalse(self.profile["inherit_personal_resources"])
        readme = (_paths.REPO_ROOT / "agent-harness" / "README.md").read_text("utf-8")
        for flag in PI_ISOLATION_FLAGS:
            self.assertIn(flag, readme, flag)

    def test_command_is_print_mode_with_exact_flags_and_tools(self) -> None:
        cmd = self.proposer.build_command(Path("/p/prompt.md"), Path("/p/session"))
        self.assertIn("--print", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], ",".join(PI_STOCK_TOOLS))
        for flag in PI_ISOLATION_FLAGS:
            self.assertEqual(cmd.count(flag), 1, flag)
        self.assertNotIn("--approve", cmd)
        self.assertEqual(cmd[-1], "@/p/prompt.md")

    def test_env_is_scrubbed_and_key_passed_only_by_configured_name(self) -> None:
        fake = {
            "PATH": "/usr/bin",
            "HOME": "/h",
            "HARNESS_TEST_KEY": "sk-test-not-real",
            "OTHER_API_KEY": "leak",
            "GITHUB_TOKEN": "leak",
            "AWS_SECRET_ACCESS_KEY": "leak",
        }
        with mock.patch.dict(os.environ, fake, clear=True):
            env = self.proposer.build_env()
        self.assertEqual(env.get("HARNESS_TEST_KEY"), "sk-test-not-real")
        for leaked in ("OTHER_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(leaked, env)
        self.assertEqual(env["PI_CODING_AGENT_DIR"], str(self.cfg.agent_dir))
        self.assertTrue(env["PI_CODING_AGENT_DIR"].startswith(self.tmp.name))

    def test_propose_without_key_fails_fast_and_offline(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
            self.assertFalse(self.proposer.api_key_present())
            with mock.patch.object(proposers.procs, "run") as run:
                with self.assertRaises(ProposerError):
                    self.proposer.propose(_context(Path(self.tmp.name), Path(self.tmp.name)))
                run.assert_not_called()

    def test_prompt_never_contains_key_value(self) -> None:
        with mock.patch.dict(os.environ, {"HARNESS_TEST_KEY": "sk-secret-value"}, clear=False):
            root = Path(self.tmp.name)
            prompt = self.proposer.render_prompt(
                _context(root, root), root / "out.patch", root / "out.json"
            )
        self.assertNotIn("sk-secret-value", prompt)
        self.assertIn("program", prompt)


if __name__ == "__main__":
    unittest.main()
