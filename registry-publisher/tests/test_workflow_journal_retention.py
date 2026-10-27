"""Exercise recovery artifacts selected by the inactive workflow templates."""

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import publish_baseline_config_only as publisher  # noqa: E402


def literal_artifact_paths(template):
    """Read this template's literal upload-artifact path scalar or block."""
    blocks = template.split("- uses: actions/upload-artifact@v4")
    if len(blocks) != 2:
        raise AssertionError("expected one explicit recovery-artifact step")
    match = re.search(r"(?m)^( +)path:(.*)$", blocks[1])
    if match is None:
        raise AssertionError("artifact step needs a literal path")
    value = match[2].strip()
    if value != "|":
        return [value]
    indent = len(match[1])
    paths = []
    for line in blocks[1][match.end() :].splitlines():
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        paths.append(line.strip())
    return paths


class RecoveryArtifactTest(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=ROOT / "tmp"))

    def tearDown(self):
        assert self.tmp.resolve().is_relative_to((ROOT / "tmp").resolve())
        shutil.rmtree(self.tmp)

    def check_failed_final_artifact(self, mode):
        name = "receipt-execute.json" if mode == "execute" else "receipt-inspection.json"
        payload = {
            "fixture": True,
            "real_registry_upload": False,
            "mode": mode,
            "partial_remote_objects_possible": mode == "execute",
        }
        final = self.tmp / name
        attempt = publisher.ReceiptAttempt(final, payload)
        try:
            attempt.record("EXECUTION_IN_PROGRESS" if mode == "execute" else "INSPECTING", payload)

            def interrupted(raw):
                attempt.final.write(b'{"interrupted":')
                attempt.final.flush()
                raise OSError("closed fixture: interrupted final write")

            with mock.patch.object(attempt, "_write_final", side_effect=interrupted):
                with self.assertRaises(OSError):
                    attempt.finish(payload)
        finally:
            attempt.close()
        journal = final.with_name(final.name + ".attempt.jsonl")
        events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[-1]["event"], "FINAL_RECEIPT_FAILED")
        self.assertEqual(final.read_bytes(), b'{"interrupted":')
        template = (ROOT / "workflow" / f"{mode}-baseline-config-only.yml").read_text(
            encoding="utf-8"
        )
        artifact = template.split("- uses: actions/upload-artifact@v4")[1]
        self.assertIn("if: always()", artifact)
        selected = {
            path.name
            for pattern in literal_artifact_paths(template)
            for path in self.tmp.glob(pattern)
        }
        self.assertIn(final.name, selected)
        self.assertIn(journal.name, selected)

    def test_execute_failure_retains_its_durable_journal_in_artifact(self):
        self.check_failed_final_artifact("execute")

    def test_inspection_failure_retains_its_durable_journal_in_artifact(self):
        self.check_failed_final_artifact("inspect")


if __name__ == "__main__":
    unittest.main(verbosity=2)
