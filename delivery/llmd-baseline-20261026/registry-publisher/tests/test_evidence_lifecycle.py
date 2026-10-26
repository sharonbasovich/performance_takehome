"""Closed regressions for checked executable identity and pre-client evidence."""

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "src"))
import publish_baseline_config_only as p  # noqa: E402
import test_publish_baseline_config_only as baseline  # noqa: E402


class EvidenceLifecycle(unittest.TestCase):
    setUp = baseline.PublisherTest.setUp
    tearDown = baseline.PublisherTest.tearDown
    args = baseline.PublisherTest.args
    receipt_json = baseline.PublisherTest.receipt_json
    sel_sha = baseline.PublisherTest.sel_sha

    def execute_args(self):
        return self.args("--execute", "--root-approved-selection-sha256", self.sel_sha())

    def journal(self):
        return self.receipt.with_name(self.receipt.name + ".attempt.jsonl")

    def events(self):
        return [json.loads(line) for line in self.journal().read_text().splitlines()]

    @unittest.skipUnless(os.name == "posix", "functional ./binary launch requires POSIX")
    def test_relative_checked_binary_launches_without_cwd_in_PATH(self):
        binary = self.tmp / "regctl"
        binary.write_bytes(b"#!/bin/sh\nprintf checked-local-binary\n")
        binary.chmod(0o700)
        previous = Path.cwd()
        try:
            os.chdir(self.tmp)
            with mock.patch.object(
                p, "REGCTL_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest()
            ):
                client = p.RegctlClient(Path("./regctl"))
            with mock.patch.dict(os.environ, {"PATH": "/does-not-contain-current-directory"}):
                self.assertEqual(client._run("fixture"), "checked-local-binary")
            self.assertEqual(client.bin, str(binary.absolute()))
        finally:
            os.chdir(previous)

    def test_missing_receipt_parent_refuses_before_client_creation(self):
        args = self.execute_args()
        self.receipt = self.tmp / "missing" / "receipt.json"
        args[args.index("--receipt") + 1] = str(self.receipt)
        created = []
        fake = baseline.FakeRegistry()

        def factory():
            created.append(True)
            return fake

        self.assertEqual(p.main(args, client_factory=factory), 65)
        self.assertEqual(created, [])
        self.assertEqual(fake.calls, [])
        self.assertFalse(fake.manifests)

    def test_unwritable_receipt_refuses_before_client_creation(self):
        args = self.execute_args()
        real_open = p.os.open

        def denied(path, *a, **kw):
            if Path(path) == self.receipt.absolute():
                raise PermissionError("closed fixture: receipt unavailable")
            return real_open(path, *a, **kw)

        factory = mock.Mock()
        with mock.patch.object(p.os, "open", side_effect=denied):
            self.assertEqual(p.main(args, client_factory=factory), 65)
            factory.assert_not_called()

    def test_initial_journal_sync_failure_refuses_before_client_creation(self):
        args = self.execute_args()
        factory = mock.Mock()
        with mock.patch.object(p.os, "fsync", side_effect=OSError("closed fixture: sync failed")):
            self.assertEqual(p.main(args, client_factory=factory), 65)
        factory.assert_not_called()
        self.assertTrue(self.receipt.exists())
        self.assertTrue(self.journal().exists())

    def test_execution_record_and_original_receipt_handle_precede_client(self):
        args = self.execute_args()
        fake = baseline.FakeRegistry()
        identities = []

        def factory():
            self.assertEqual(self.events()[-1]["event"], "EXECUTION_IN_PROGRESS")
            self.assertEqual(self.events()[-1]["result"], "EXECUTION_IN_PROGRESS")
            self.assertTrue(self.events()[-1]["partial_remote_objects_possible"])
            info = self.receipt.stat()
            identities.append((info.st_dev, info.st_ino))
            return fake

        self.assertEqual(p.main(args, client_factory=factory), 0)
        info = self.receipt.stat()
        self.assertEqual(identities, [(info.st_dev, info.st_ino)])
        self.assertEqual(self.events()[-1]["event"], "FINAL_RECEIPT_SAVED")
        self.assertEqual(
            self.events()[-1]["receipt_sha256"],
            hashlib.sha256(self.receipt.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.receipt_json()["result"], "FIXTURE_VALIDATED_NO_REAL_UPLOAD")

    def test_existing_attempt_journal_is_preserved_without_client(self):
        args = self.execute_args()
        self.journal().write_bytes(b"earlier uncertain attempt\n")
        factory = mock.Mock()
        self.assertEqual(p.main(args, client_factory=factory), 65)
        factory.assert_not_called()
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.journal().read_bytes(), b"earlier uncertain attempt\n")

    @unittest.skipUnless(os.name == "posix", "replacement of an open file is a POSIX case")
    def test_replaced_receipt_is_never_overwritten_or_published(self):
        args = self.execute_args()
        fake = baseline.FakeRegistry()
        owned = self.tmp / "owned-reserved-receipt"

        def factory():
            self.receipt.rename(owned)
            self.receipt.write_bytes(b"different attempt receipt")
            return fake

        self.assertEqual(p.main(args, client_factory=factory), 65)
        self.assertEqual(self.receipt.read_bytes(), b"different attempt receipt")
        self.assertEqual(owned.read_bytes(), b"")
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.events()[-1]["event"], "EXECUTION_IN_PROGRESS")

    def test_failed_final_write_preserves_execution_journal(self):
        args = self.execute_args()
        fake = baseline.FakeRegistry()

        def fail_after_partial(attempt, raw):
            attempt.final.write(b'{"interrupted":')
            attempt.final.flush()
            raise OSError("closed fixture: final write failed")

        with mock.patch.object(p.ReceiptAttempt, "_write_final", fail_after_partial):
            self.assertEqual(p.main(args, client_factory=lambda: fake), 65)
        self.assertTrue(fake.manifests)
        self.assertEqual(self.receipt.read_bytes(), b'{"interrupted":')
        self.assertEqual(self.events()[-1]["event"], "FINAL_RECEIPT_FAILED")
        self.assertTrue(self.events()[-1]["partial_remote_objects_possible"])

    def test_constructor_failure_retains_conservative_execution_state(self):
        args = self.execute_args()

        def fail():
            raise p.Refused("closed fixture: client construction failed")

        self.assertEqual(p.main(args, client_factory=fail), 65)
        self.assertEqual(self.receipt_json()["result"], "REFUSED")
        self.assertTrue(self.receipt_json()["partial_remote_objects_possible"])
        self.assertEqual(self.events()[1]["event"], "EXECUTION_IN_PROGRESS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
