"""Regression for the delivery contract independently identified after revision 2."""

import copy
import json
import sys
import unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "src"))
import publish_baseline_config_only as p  # noqa: E402 - explicit standalone source path
import test_publish_baseline_config_only as baseline_tests  # noqa: E402


class SelectionContractTests(unittest.TestCase):
    setUp = baseline_tests.PublisherTest.setUp
    tearDown = baseline_tests.PublisherTest.tearDown
    args = baseline_tests.PublisherTest.args
    receipt_json = baseline_tests.PublisherTest.receipt_json
    sel_sha = baseline_tests.PublisherTest.sel_sha

    def test_current_selection_binds_platform_and_mutable_tag_in_inspection(self):
        fake = baseline_tests.FakeRegistry()
        self.assertEqual(p.main(self.args(), client_factory=lambda: fake), 0)
        contract = self.receipt_json()["validation"]["selection"]["destination"]
        self.assertEqual(contract, p.EXPECTED_DESTINATION)
        self.assertTrue(contract["tag_is_mutable"])
        self.assertFalse(contract["original_index_published"])
        self.assertEqual(fake.calls, [])

    def test_stale_or_unbound_destination_refused_before_any_client_operation(self):
        original = json.loads(self.sel.read_bytes())
        cases = [
            (
                "stale original index",
                lambda d: d.__setitem__("by_digest", p.DESTINATION + "@" + p.EXPECTED_INDEX),
            ),
            (
                "foreign registry",
                lambda d: d.__setitem__("registry", "ghcr.io/unapproved/other"),
            ),
            (
                "foreign digest reference",
                lambda d: d.__setitem__(
                    "by_digest", "ghcr.io/unapproved/other@" + p.EXPECTED_MANIFEST
                ),
            ),
            ("unreviewed tag", lambda d: d.__setitem__("mutable_tag", "latest")),
            (
                "obsolete immutable tag",
                lambda d: d.__setitem__("immutable_tag", p.PUBLICATION_TAG),
            ),
            ("missing mutable flag", lambda d: d.pop("tag_is_mutable")),
            ("numeric mutable flag", lambda d: d.__setitem__("tag_is_mutable", 1)),
            (
                "claims index publication",
                lambda d: d.__setitem__("original_index_published", True),
            ),
            (
                "wrong object type",
                lambda d: d.__setitem__("published_object", "original_index"),
            ),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                selection = copy.deepcopy(original)
                mutate(selection["destination"])
                self.sel.write_text(json.dumps(selection), encoding="utf-8")
                fake = baseline_tests.FakeRegistry()
                self.assertEqual(
                    p.main(
                        self.args(
                            "--execute",
                            "--root-approved-selection-sha256",
                            self.sel_sha(),
                        ),
                        client_factory=lambda fake=fake: fake,
                    ),
                    65,
                )
                self.assertIn("selection destination", self.receipt_json()["reason"])
                self.assertEqual(fake.calls, [])

    def test_schema_and_legacy_selection_cannot_be_promoted_as_current(self):
        original = json.loads(self.sel.read_bytes())
        for version in (1, 2.0, True, "2", None):
            with self.subTest(version=version):
                selection = copy.deepcopy(original)
                selection["schema_version"] = version
                with self.assertRaisesRegex(p.Refused, "schema_version"):
                    p.validate_selection(json.dumps(selection).encode(), self.df.read_bytes())
        with self.assertRaisesRegex(p.Refused, "schema_version"):
            p.validate_selection(
                (R / "evidence/legacy-selection-revision2.json").read_bytes(),
                self.df.read_bytes(),
            )
        for raw in (b"[]", b"null", b"true"):
            with self.assertRaisesRegex(p.Refused, "schema_version"):
                p.validate_selection(raw, self.df.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
