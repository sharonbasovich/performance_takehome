"""Timeouts kill the whole process group (hung engine / build / proposer)."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from abstract_harness import procs

from . import _paths  # noqa: F401


class ProcessGroupTest(unittest.TestCase):
    def test_timeout_kills_child_and_grandchild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "pid"
            script = f"sleep 300 & echo $! > {pidfile}; wait"
            t0 = time.monotonic()
            result = procs.run(["bash", "-c", script], timeout_s=1.0)
            self.assertTrue(result.timed_out)
            self.assertFalse(result.ok)
            self.assertLess(time.monotonic() - t0, 10)
            grandchild = int(pidfile.read_text().strip())
            time.sleep(0.2)
            with self.assertRaises(ProcessLookupError):
                os.kill(grandchild, 0)

    def test_successful_run_captures_output_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "run.log"
            result = procs.run(
                ["bash", "-c", "echo out; echo err 1>&2"], timeout_s=10, log_path=log
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.returncode, 0)
            self.assertIn("out", result.stdout + log.read_text())
            self.assertFalse(result.timed_out)

    def test_nonzero_exit_is_not_ok(self) -> None:
        result = procs.run(["bash", "-c", "exit 3"], timeout_s=10)
        self.assertEqual(result.returncode, 3)
        self.assertFalse(result.ok)

    def test_kill_process_group_on_already_dead_process_is_safe(self) -> None:
        proc = subprocess.Popen(["true"], start_new_session=True)
        proc.wait()
        procs.kill_process_group(proc)


if __name__ == "__main__":
    unittest.main()
