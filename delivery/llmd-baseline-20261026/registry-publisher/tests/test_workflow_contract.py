import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "src"))
import check_publication_approval as check  # noqa: E402 - explicit standalone source path


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=R / "tmp"))
        self.root = self.tmp / "registry-publisher"
        for part in ("src", "workflow", "evidence"):
            shutil.copytree(R / part, self.root / part)
        p = self.tmp / ".github/workflows"
        p.mkdir(parents=True)
        shutil.copyfile(
            R / "workflow/execute-baseline-config-only.yml",
            p / "execute-baseline-config-only.yml",
        )

    def tearDown(self):
        assert self.tmp.resolve().is_relative_to((R / "tmp").resolve())
        shutil.rmtree(self.tmp)

    def approval(self):
        p = {
            "repository": check.REPOSITORY,
            "ref": check.REF,
            "acknowledge_baseline_fallback": True,
            "acknowledge_private_package_access_pending": True,
        }
        for field, name in [
            ("selection_sha256", "evidence/selection.json"),
            ("publisher_sha256", "src/publish_baseline_config_only.py"),
            ("checker_sha256", "src/check_publication_approval.py"),
            ("execute_workflow_sha256", "workflow/execute-baseline-config-only.yml"),
        ]:
            p[field] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        (self.root / "evidence/PUBLICATION_APPROVAL.json").write_text(json.dumps(p))
        return p

    def test_no_marker_no_execution(self):
        with self.assertRaises(OSError):
            check.check(self.root, check.REPOSITORY, check.REF)
        self.assertFalse((R / "evidence/PUBLICATION_APPROVAL.json").exists())

    def test_valid_marker_and_wrong_branch_or_edited_source_refuse(self):
        p = self.approval()
        self.assertEqual(check.check(self.root, check.REPOSITORY, check.REF), p["selection_sha256"])
        with self.assertRaises(ValueError):
            check.check(self.root, check.REPOSITORY, "refs/heads/ordinary-pr")
        (self.root / "src/publish_baseline_config_only.py").write_text("changed")
        with self.assertRaises(ValueError):
            check.check(self.root, check.REPOSITORY, check.REF)

    def test_alternate_running_workflow_and_shell_payload_refuse(self):
        p = self.approval()
        (self.tmp / ".github/workflows/execute-baseline-config-only.yml").write_text("changed")
        with self.assertRaises(ValueError):
            check.check(self.root, check.REPOSITORY, check.REF)
        p["selection_sha256"] = "$(touch bad)"
        (self.root / "evidence/PUBLICATION_APPROVAL.json").write_text(json.dumps(p))
        with self.assertRaises(ValueError):
            check.check(self.root, check.REPOSITORY, check.REF)

    def test_legacy_selection_approval_cannot_authorize_corrected_contract(self):
        p = self.approval()
        legacy = (R / "evidence/legacy-selection-revision2.json").read_bytes()
        self.assertNotEqual(hashlib.sha256(legacy).hexdigest(), p["selection_sha256"])
        p["selection_sha256"] = hashlib.sha256(legacy).hexdigest()
        (self.root / "evidence/PUBLICATION_APPROVAL.json").write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            check.check(self.root, check.REPOSITORY, check.REF)

    def test_workflows_have_no_shell_interpolated_dispatch_input(self):
        inspect = (R / "workflow/inspect-baseline-config-only.yml").read_text()
        execute = (R / "workflow/execute-baseline-config-only.yml").read_text()
        for text in (inspect, execute):
            self.assertNotIn("${{ inputs.", text)
            self.assertIn("github.event.repository.private == false", text)
            self.assertNotIn("workflow_dispatch:", text)
        self.assertNotIn("--execute", inspect)
        self.assertNotIn("packages: write", inspect)
        self.assertLess(
            execute.index("check_publication_approval.py"),
            execute.index("./regctl registry login"),
        )
        self.assertIn("GHCR_TOKEN: ${{ secrets.GITHUB_TOKEN }}", execute)
        self.assertNotIn("<<<", execute)


if __name__ == "__main__":
    unittest.main(verbosity=2)
