import json
import sys
import time
import unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "src"))
import publish_baseline_config_only as p  # noqa: E402 - explicit standalone source path
import test_publish_baseline_config_only as baseline_tests  # noqa: E402

FakeRegistry = baseline_tests.FakeRegistry


class Regressions(unittest.TestCase):
    setUp = baseline_tests.PublisherTest.setUp
    tearDown = baseline_tests.PublisherTest.tearDown
    args = baseline_tests.PublisherTest.args
    receipt_json = baseline_tests.PublisherTest.receipt_json
    sel_sha = baseline_tests.PublisherTest.sel_sha
    _refuse = baseline_tests.PublisherTest._refuse

    def test_foreign_destination_refused_before_remote(self):
        fake = FakeRegistry()
        rc = p.main(
            self.args(
                "--execute",
                "--root-approved-selection-sha256",
                self.sel_sha(),
                "--destination",
                "ghcr.io/unapproved/other",
            ),
            client_factory=lambda: fake,
        )
        self.assertEqual(rc, 65)
        self.assertEqual(fake.calls, [])

    def test_index_child_closure_platform_only(self):
        class Closure(FakeRegistry):
            def put_manifest(self, repo, data, kind, ref):
                if kind == p.MT_INDEX:
                    raise AssertionError("Original two-child index must not be published")
                for descriptor in [
                    json.loads(data)["config"],
                    *json.loads(data)["layers"],
                ]:
                    if descriptor["digest"] not in self.blobs.get(repo, set()):
                        raise p.Refused("fake missing blob")
                super().put_manifest(repo, data, kind, ref)

        fake = Closure()
        rc = p.main(
            self.args("--execute", "--root-approved-selection-sha256", self.sel_sha()),
            client_factory=lambda: fake,
        )
        self.assertEqual(rc, 0)
        self.assertFalse(self.receipt_json()["publication"]["original_index_published"])
        self.assertEqual(
            self.receipt_json()["publication"]["reference"],
            p.DESTINATION + "@" + p.EXPECTED_MANIFEST,
        )

    def test_duplicate_nonfinite_and_malformed_selection_refused(self):
        original = self.sel.read_bytes()
        bad = [
            b"{",
            original.rstrip().removesuffix(b"}") + b',"status":"BASELINE_FALLBACK"}',
            b'{"status":NaN}',
        ]
        for data in bad:
            self.sel.write_bytes(data)
            fake = self._refuse("JSON")
            self.assertEqual(fake.calls, [])

    def test_bounded_file_load(self):
        huge = self.tmp / "large"
        huge.write_bytes(b"x" * (p.MAX_METADATA_BYTES + 1))
        with self.assertRaises(p.Refused):
            p._load(huge)

    def test_existing_receipt_refuses_without_overwrite(self):
        a = self.args("--execute", "--root-approved-selection-sha256", self.sel_sha())
        self.receipt.write_bytes(b"original")
        fake = FakeRegistry()
        self.assertEqual(p.main(a, client_factory=lambda: fake), 65)
        self.assertEqual(self.receipt.read_bytes(), b"original")
        self.assertEqual(fake.calls, [])

    def test_approval_shell_payload_refused_before_remote(self):
        fake = FakeRegistry()
        self.assertEqual(
            p.main(
                self.args("--execute", "--root-approved-selection-sha256", "$(touch bad)"),
                client_factory=lambda: fake,
            ),
            65,
        )
        self.assertEqual(fake.calls, [])

    def test_timeout_failure_receipt_and_partial_flag(self):
        class Timeout(FakeRegistry):
            def copy_blob(self, *a):
                raise p.subprocess.TimeoutExpired(["fake"], 0.1)

        self.assertEqual(
            p.main(
                self.args("--execute", "--root-approved-selection-sha256", self.sel_sha()),
                client_factory=Timeout,
            ),
            65,
        )
        self.assertTrue(self.receipt_json()["partial_remote_objects_possible"])
        self.assertFalse(self.receipt_json()["uploaded"])

    def test_pinned_client_runner_real_child_deadline_no_network(self):
        client = p.RegctlClient.__new__(p.RegctlClient)
        client.bin = sys.executable
        client.end = time.monotonic() + 0.15
        start = time.monotonic()
        with self.assertRaises(p.Refused):
            client._run("-c", "import time; time.sleep(10)", stdin=b"x" * 65536)
        self.assertLess(time.monotonic() - start, 3)

    def test_pinned_client_runner_output_cap_no_network(self):
        client = p.RegctlClient.__new__(p.RegctlClient)
        client.bin = sys.executable
        client.end = time.monotonic() + 3
        with self.assertRaises(p.Refused):
            client._run("-c", 'import sys; sys.stdout.write("x"*2000000)')


if __name__ == "__main__":
    unittest.main(verbosity=2)
