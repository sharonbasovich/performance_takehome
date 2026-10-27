"""CPU-only tests: real accepted small metadata + a closed fake registry client. No network."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
import publish_baseline_config_only as pub  # noqa: E402 - explicit standalone source path

DELIVERY = HERE.parent / "delivery"
(HERE.parent / "tmp").mkdir(exist_ok=True)
SELECTION = HERE.parent / "evidence" / "selection.json"


class FakeRegistry:
    def __init__(self, fail_upload: bool = False, readback_override: dict | None = None):
        self.blobs: dict[str, set[str]] = {}
        self.manifests: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.fail_upload = fail_upload
        self.readback_override = readback_override or {}
        self.calls: list[str] = []

    def blob_exists(self, repo, digest):
        self.calls.append(f"head {digest[:19]}")
        return digest in self.blobs.get(repo, set())

    def copy_blob(self, src_repo, dst_repo, digest, size):
        self.calls.append(f"copy {digest[:19]}")
        if self.fail_upload:
            raise pub.Refused("fake registry: blob copy failed (simulated 502)")
        self.blobs.setdefault(dst_repo, set()).add(digest)

    def put_blob(self, repo, data, digest):
        if pub.digest_of(data) != digest:
            raise pub.Refused("fake registry: blob digest mismatch")
        self.blobs.setdefault(repo, set()).add(digest)

    def put_manifest(self, repo, data, media_type, reference):
        self.manifests[(repo, reference)] = (data, media_type)
        if reference.startswith("sha256:") and pub.digest_of(data) != reference:
            raise pub.Refused("fake registry: manifest digest mismatch")

    def head_manifest(self, repo, reference):
        if reference in self.readback_override:
            return self.readback_override[reference]
        data, _ = self.manifests[(repo, reference)]
        return pub.digest_of(data)


class PublisherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=HERE.parent / "tmp"))
        self.meta = self.tmp / "metadata"
        shutil.copytree(DELIVERY / "metadata", self.meta)
        self.base = self.tmp / "base-manifest.json"
        shutil.copy(DELIVERY / "base-manifest.json", self.base)
        self.df = self.tmp / "selected.Dockerfile"
        shutil.copy(DELIVERY / "selected.Dockerfile", self.df)
        self.sel = self.tmp / "selection.json"
        shutil.copy(SELECTION, self.sel)
        self.receipt = self.tmp / "receipt.json"

    def tearDown(self):
        assert self.tmp.resolve().is_relative_to((HERE.parent / "tmp").resolve())
        shutil.rmtree(self.tmp)

    def args(self, *extra):
        self.receipt = self.tmp / (
            "receipt-" + str(len(list(self.tmp.glob("receipt-*.json")))) + ".json"
        )
        return [
            "--metadata-dir",
            str(self.meta),
            "--base-manifest",
            str(self.base),
            "--dockerfile",
            str(self.df),
            "--selection",
            str(self.sel),
            "--receipt",
            str(self.receipt),
            *extra,
        ]

    def receipt_json(self):
        return json.loads(self.receipt.read_text())

    def sel_sha(self):
        return hashlib.sha256(self.sel.read_bytes()).hexdigest()

    def test_inspection_default_validates_and_uploads_nothing(self):
        fake = FakeRegistry()
        rc = pub.main(self.args(), client_factory=lambda: fake)
        r = self.receipt_json()
        self.assertEqual((rc, r["result"], r["uploaded"]), (0, "VALIDATED_NOT_UPLOADED", False))
        self.assertEqual(fake.calls, [])
        self.assertTrue(r["validation"]["layers_identical_to_base"])
        self.assertEqual(r["validation"]["compressed_layer_bytes"], 5923157643)
        self.assertEqual(r["validation"]["selection"]["status"], "BASELINE_FALLBACK")

    def test_execute_success_returns_exact_platform_reference(self):
        fake = FakeRegistry()
        rc = pub.main(
            self.args("--execute", "--root-approved-selection-sha256", self.sel_sha()),
            client_factory=lambda: fake,
        )
        r = self.receipt_json()
        self.assertEqual(
            (rc, r["result"], r["uploaded"]),
            (0, "FIXTURE_VALIDATED_NO_REAL_UPLOAD", False),
        )
        self.assertFalse(r["real_registry_upload"])
        self.assertEqual(
            r["publication"]["reference"], f"{pub.DESTINATION}@{pub.EXPECTED_MANIFEST}"
        )
        self.assertEqual(r["publication"]["readback_tag_digest"], pub.EXPECTED_MANIFEST)
        self.assertEqual(len([c for c in fake.calls if c.startswith("copy")]), 23)
        self.assertEqual(
            fake.manifests[(pub.DESTINATION, pub.PUBLICATION_TAG)][0],
            (
                self.meta
                / "001-7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d.bin"
            ).read_bytes(),
        )

    def test_execute_without_root_approval_hash_refused(self):
        fake = FakeRegistry()
        rc = pub.main(self.args("--execute"), client_factory=lambda: fake)
        self.assertEqual((rc, self.receipt_json()["result"]), (65, "REFUSED"))
        self.assertIn("root-approved", self.receipt_json()["reason"])
        self.assertEqual(fake.calls, [])
        rc = pub.main(
            self.args("--execute", "--root-approved-selection-sha256", "0" * 64),
            client_factory=lambda: fake,
        )
        self.assertEqual(rc, 65)

    def _refuse(self, needle, *extra):
        fake = FakeRegistry()
        rc = pub.main(self.args(*extra), client_factory=lambda: fake)
        r = self.receipt_json()
        self.assertEqual((rc, r["result"], r["uploaded"]), (65, "REFUSED", False), r)
        self.assertIn(needle, r["reason"])
        return fake

    def test_wrong_config_bytes_refused(self):
        p = self.meta / "000-0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f.bin"
        p.write_bytes(p.read_bytes().replace(b'"User":"0"', b'"User":"1"'))
        self._refuse("accepted config digest")

    def test_wrong_layers_refused(self):
        b = json.loads(self.base.read_bytes())
        b["layers"][5]["digest"] = "sha256:" + "ab" * 32
        self.base.write_text(json.dumps(b))
        self._refuse("public base digest")
        # hash-independent structural check also refuses
        with self.assertRaises(pub.Refused):
            pub.validate_structure(
                *(
                    DELIVERY.joinpath("metadata", n).read_bytes()
                    for n in (
                        "000-0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f.bin",
                        "001-7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d.bin",
                        "002-ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540.bin",
                    )
                ),
                self.base.read_bytes(),
                self.df.read_bytes(),
            )

    def test_new_env_or_history_refused_structurally(self):
        cfg = json.loads(
            (
                DELIVERY
                / "metadata"
                / "000-0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f.bin"
            ).read_bytes()
        )
        man = (
            DELIVERY
            / "metadata"
            / "001-7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d.bin"
        ).read_bytes()
        idx = (
            DELIVERY
            / "metadata"
            / "002-ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540.bin"
        ).read_bytes()
        base = self.base.read_bytes()
        df = self.df.read_bytes()
        good = json.loads(man)
        for mutate, needle in (
            (
                lambda c: c["config"]["Env"].append("NEW_SECRET=ghp_" + "x" * 36),
                "Env keys",
            ),
            (
                lambda c: c["history"].append({"created_by": "RUN echo"}),
                "history length",
            ),
            (
                lambda c: c["config"].__setitem__("Cmd", ["--io-impl=zio"]),
                "Entrypoint/Cmd",
            ),
        ):
            c = json.loads(json.dumps(cfg))
            mutate(c)
            cb = json.dumps(c, separators=(",", ":")).encode()
            m = json.loads(json.dumps(good))
            m["config"]["digest"], m["config"]["size"] = pub.digest_of(cb), len(cb)
            with self.assertRaises(pub.Refused) as ctx:
                pub.validate_structure(cb, json.dumps(m).encode(), idx, base, df)
            self.assertIn(needle, str(ctx.exception))

    def test_changed_dockerfile_refused(self):
        self.df.write_text(self.df.read_text().replace('"--batch-size=16"', '"--batch-size=32"'))
        self._refuse("Entrypoint/Cmd")

    def test_selection_wrong_model_source_or_missing_caveats_refused(self):
        s = json.loads(self.sel.read_text())
        cases = [
            (lambda d: d["model"].__setitem__("revision", "deadbeef"), "model"),
            (lambda d: d["source"].__setitem__("commit", "0" * 40), "source commit"),
            (lambda d: d.__setitem__("status", "REAL_PI_LAST_GOOD"), "status"),
            (
                lambda d: d["pi_attempt"].__setitem__("outcome", "kept"),
                "failed_before_patch",
            ),
            (
                lambda d: d.__setitem__("optimized_gain_claimed", True),
                "optimized_gain_claimed",
            ),
            (
                lambda d: d["fresh_revalidation"].__setitem__("raw_report_retained", True),
                "retention gap",
            ),
            (
                lambda d: d["image"].__setitem__("config", "sha256:" + "00" * 32),
                "image identities",
            ),
            (lambda d: d.__setitem__("archive_sha256", "11" * 32), "archive hashes"),
        ]
        for mutate, needle in cases:
            d = json.loads(json.dumps(s))
            mutate(d)
            self.sel.write_text(json.dumps(d, indent=2))
            self._refuse(needle)

    def test_failed_upload_preserves_failure_receipt(self):
        fake = FakeRegistry(fail_upload=True)
        rc = pub.main(
            self.args("--execute", "--root-approved-selection-sha256", self.sel_sha()),
            client_factory=lambda: fake,
        )
        r = self.receipt_json()
        self.assertEqual(
            (rc, r["result"], r["uploaded"], r["mode"]),
            (65, "REFUSED", False, "execute"),
        )
        self.assertIn("blob copy failed", r["reason"])

    def test_mismatched_or_mutable_readback_refused(self):
        fake = FakeRegistry(readback_override={pub.PUBLICATION_TAG: "sha256:" + "ff" * 32})
        rc = pub.main(
            self.args("--execute", "--root-approved-selection-sha256", self.sel_sha()),
            client_factory=lambda: fake,
        )
        r = self.receipt_json()
        self.assertEqual((rc, r["result"], r["uploaded"]), (65, "REFUSED", False))
        self.assertIn("mutable/mismatched", r["reason"])

    def test_unreviewed_mutable_tag_refused(self):
        b = pub.load_bundle(self.meta, self.base, self.df, self.sel)
        with self.assertRaises(pub.Refused):
            pub.publish(b, FakeRegistry(), tag="latest")

    def test_regctl_pin_enforced(self):
        fake_bin = self.tmp / "regctl"
        fake_bin.write_bytes(b"not regctl")
        with self.assertRaises(pub.Refused) as ctx:
            pub.RegctlClient(fake_bin)
        self.assertIn(pub.REGCTL_SHA256, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
