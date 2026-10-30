#!/usr/bin/env python3
"""Config-only registry publisher candidate for the exact measured LLMD baseline.

Default mode is INSPECTION ONLY: it validates the raw exported OCI metadata against the
accepted baseline identities and the selection evidence, writes a receipt, and uploads
nothing. Uploading requires ``--execute`` plus ``--root-approved-selection-sha256`` equal
to the SHA-256 of the selection file. Image bytes are never rebuilt or re-serialized:
the raw config and selected platform manifest are pushed byte-for-byte and the 23
inherited layers are copied by digest from the public base repository (stream copy; no
Docker unpack). Evidence paths are exclusively reserved before client construction;
a durable attempt journal retains execution uncertainty if the final receipt fails.
Success requires the registry read-back digest to equal the pinned platform digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

EXPECTED_INDEX = "sha256:ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540"
EXPECTED_MANIFEST = "sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d"
EXPECTED_CONFIG = "sha256:0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f"
EXPECTED_BASE_MANIFEST = "sha256:0a2cd01a2e53c78934a8cfef66f8668da7666be4954a5d18b72df089c54ea34f"
EXPECTED_DOCKERFILE_SHA256 = "7f8caeabc5b52b2fe1406287a57317bc6e56c7adb0a63e576a4710afe76a1225"
EXPECTED_LAYER_COUNT = 23
EXPECTED_ENV_KEYS = (
    "PATH",
    "SSL_CERT_FILE",
    "LLMD_POSTHOG_TOKEN",
    "LLMD_USAGE_STATS_ENDPOINT",
)
EXPECTED_HISTORY_LEN = 25
EXPECTED_SOURCE_COMMIT = "09f52c25af380a0daefdea3a183fe45a6ec75730"
EXPECTED_MODEL = {
    "repository": "Qwen/Qwen3.6-27B",
    "revision": "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9",
}
EXPECTED_BASELINE_REPORT_SHA256 = "f83cadc074363d7affe2b830a45af96ecacc22e234f8857a9767a4accdc2edff"
EXPECTED_ARCHIVE_SHA256 = "c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47"
SOURCE_REPO = "docker.io/zmlai/llmd"
DESTINATION = "ghcr.io/sharonbasovich/performance_takehome-task2-llmd"
PUBLICATION_TAG = "baseline-ccd73fc2"
EXPECTED_DESTINATION = {
    "registry": DESTINATION,
    "by_digest": f"{DESTINATION}@{EXPECTED_MANIFEST}",
    "mutable_tag": PUBLICATION_TAG,
    "tag_is_mutable": True,
    "published_object": "selected_linux_amd64_platform_manifest",
    "original_index_published": False,
}
REGCTL_VERSION = "v0.11.7"
# Self-computed regctl-linux-amd64 v0.11.7 pin, not an official checksum/signature.
REGCTL_SHA256 = "3737fbbdd791e04e7a831640b681f3397a376498e80e2ad9b1b2d27296f239bc"
REQUIRED_STATUS = "BASELINE_FALLBACK"
FORBIDDEN_STATUS_WORDS = ("REAL_PI_LAST_GOOD", "OPTIMIZED", "KEPT", "LAST_GOOD")
SECRET_RE = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)"
)

MT_INDEX = "application/vnd.oci.image.index.v1+json"
MT_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
MT_CONFIG = "application/vnd.oci.image.config.v1+json"


class Refused(Exception):
    """Validation or publication refusal; the message is the receipt reason."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_of(data: bytes) -> str:
    return "sha256:" + sha256_hex(data)


MAX_METADATA_BYTES = 256 * 1024


def strict_json(raw: bytes):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_METADATA_BYTES:
        raise Refused("bounded nonempty JSON required")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise Refused("duplicate JSON key")
            out[key] = value
        return out

    def constant(value):
        raise Refused("nonfinite JSON constant")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise Refused("malformed JSON") from exc


def _load(path: Path, limit: int = MAX_METADATA_BYTES) -> bytes:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise Refused("nonredirected regular input required")
    before = path.stat()
    if not 0 < before.st_size <= limit:
        raise Refused("input exceeds explicit byte bound")
    with path.open("rb") as f:
        raw = f.read(limit + 1)
    after = path.stat()
    if (
        len(raw) != before.st_size
        or len(raw) > limit
        or (before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise Refused("input changed or exceeded byte bound")
    return raw


def dockerfile_entrypoint_cmd(text: str) -> tuple[list[str], list[str]]:
    ep = cmd = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("ENTRYPOINT "):
            ep = json.loads(s[len("ENTRYPOINT ") :])
        elif s.startswith("CMD "):
            cmd = json.loads(s[len("CMD ") :])
    if ep is None or cmd is None:
        raise Refused("selected.Dockerfile lacks exec-form ENTRYPOINT/CMD")
    return ep, cmd


@dataclass
class Bundle:
    config: bytes
    manifest: bytes
    index: bytes
    base_manifest: bytes
    dockerfile: bytes
    selection: bytes
    selection_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self.selection_sha256 = sha256_hex(self.selection)


def load_bundle(
    metadata_dir: Path, base_manifest: Path, dockerfile: Path, selection: Path
) -> Bundle:
    def meta(digest: str) -> bytes:
        hexd = digest.split(":", 1)[1]
        hits = sorted(p for p in metadata_dir.iterdir() if p.name.endswith(f"-{hexd}.bin"))
        if len(hits) != 1:
            raise Refused(f"metadata blob for {digest} not found exactly once in {metadata_dir}")
        return _load(hits[0])

    return Bundle(
        meta(EXPECTED_CONFIG),
        meta(EXPECTED_MANIFEST),
        meta(EXPECTED_INDEX),
        _load(base_manifest),
        _load(dockerfile),
        _load(selection),
    )


def validate_structure(
    config: bytes,
    manifest: bytes,
    index: bytes,
    base_manifest: bytes,
    dockerfile: bytes,
) -> dict:
    """Compare descriptors/layers/diff IDs/runtime config independently of full hashes."""
    c, m, i, b = (strict_json(x) for x in (config, manifest, index, base_manifest))
    out: dict = {}
    if m.get("mediaType") != MT_MANIFEST or i.get("mediaType") != MT_INDEX:
        raise Refused("unexpected manifest/index mediaType")
    if (
        m["config"].get("mediaType") != MT_CONFIG
        or m["config"]["digest"] != digest_of(config)
        or m["config"]["size"] != len(config)
    ):
        raise Refused(
            "platform manifest config descriptor does not describe the supplied config bytes"
        )
    layers, base_layers = m.get("layers", []), b.get("layers", [])
    if len(layers) != EXPECTED_LAYER_COUNT or len(base_layers) != EXPECTED_LAYER_COUNT:
        raise Refused(f"layer count {len(layers)}/{len(base_layers)} != {EXPECTED_LAYER_COUNT}")
    for n, (x, y) in enumerate(zip(layers, base_layers, strict=True)):
        if (x["digest"], x["size"], x["mediaType"]) != (
            y["digest"],
            y["size"],
            y["mediaType"],
        ):
            raise Refused(f"layer {n} differs from inherited public base layer")
    out["layers_identical_to_base"] = True
    out["compressed_layer_bytes"] = sum(x["size"] for x in layers)
    diff_ids = c.get("rootfs", {}).get("diff_ids", [])
    if c.get("rootfs", {}).get("type") != "layers" or len(diff_ids) != EXPECTED_LAYER_COUNT:
        raise Refused("config rootfs diff_ids count != 23")
    out["diff_ids"] = len(diff_ids)
    if (c.get("architecture"), c.get("os")) != ("amd64", "linux"):
        raise Refused("config platform is not linux/amd64")
    ep, cmd = dockerfile_entrypoint_cmd(dockerfile.decode("utf-8"))
    if c["config"].get("Entrypoint") != ep or c["config"].get("Cmd") != cmd:
        raise Refused("config Entrypoint/Cmd differ from selected.Dockerfile")
    env_keys = tuple(e.split("=", 1)[0] for e in c["config"].get("Env", []))
    if env_keys != EXPECTED_ENV_KEYS:
        raise Refused(
            f"config Env keys {env_keys} != inherited base keys (new/removed Env refused)"
        )
    hist = c.get("history", [])
    if len(hist) != EXPECTED_HISTORY_LEN:
        raise Refused(
            f"config history length {len(hist)} != {EXPECTED_HISTORY_LEN} (added history refused)"
        )
    blob_text = (config + manifest + index).decode("utf-8", "replace")
    if SECRET_RE.search(blob_text):
        raise Refused("secret-like token pattern found in image metadata")
    plat = [x for x in i["manifests"] if x.get("platform", {}).get("os") == "linux"]
    if (
        len(plat) != 1
        or plat[0]["digest"] != digest_of(manifest)
        or plat[0]["size"] != len(manifest)
    ):
        raise Refused("index does not reference the supplied platform manifest bytes exactly once")
    out["entrypoint"], out["cmd"], out["env_keys"] = ep, cmd, list(env_keys)
    return out


def validate_selection(selection: bytes, dockerfile: bytes) -> dict:
    s = strict_json(selection)
    if (
        not isinstance(s, dict)
        or type(s.get("schema_version")) is not int
        or s["schema_version"] != 2
    ):
        raise Refused("selection schema_version must be integer 2")
    destination = s.get("destination")
    if (
        not isinstance(destination, dict)
        or destination != EXPECTED_DESTINATION
        or destination.get("tag_is_mutable") is not True
        or destination.get("original_index_published") is not False
    ):
        raise Refused(
            "selection destination must exactly bind the approved platform digest and mutable tag"
        )
    if s.get("status") != REQUIRED_STATUS:
        raise Refused("selection status must be BASELINE_FALLBACK")
    for key in ("status", "publication_state"):
        for w in FORBIDDEN_STATUS_WORDS:
            if re.search(rf"\b{w}\b", str(s.get(key, ""))) and not re.search(
                rf"\bNOT\b[^.]*\b{w}\b", str(s.get(key, ""))
            ):
                raise Refused(f"selection {key} claims forbidden outcome {w!r}")
    pi = s.get("pi_attempt", {})
    if pi.get("outcome") != "failed_before_patch" or pi.get("patch_produced") is not False:
        raise Refused(
            "selection must record the genuine Pi attempt as failed_before_patch with no patch"
        )
    if s.get("optimized_gain_claimed") is not False:
        raise Refused("selection must state optimized_gain_claimed=false")
    fr = s.get("fresh_revalidation", {})
    if fr.get("raw_report_retained") is not False or fr.get("execution_receipt_pass") is not True:
        raise Refused(
            "selection must disclose the fresh-revalidation raw report/traces "
            "retention gap with the PASS receipt"
        )
    ids = s.get("image", {})
    if (ids.get("index"), ids.get("platform_manifest"), ids.get("config")) != (
        EXPECTED_INDEX,
        EXPECTED_MANIFEST,
        EXPECTED_CONFIG,
    ):
        raise Refused("selection image identities differ from the accepted baseline")
    if s.get("source", {}).get("commit") != EXPECTED_SOURCE_COMMIT:
        raise Refused("selection source commit differs from reviewed Task 2 runtime source")
    if s.get("model") != EXPECTED_MODEL:
        raise Refused("selection model repository/revision differs from the pinned baseline model")
    if (
        s.get("source", {}).get("dockerfile_sha256") != sha256_hex(dockerfile)
        or sha256_hex(dockerfile) != EXPECTED_DOCKERFILE_SHA256
    ):
        raise Refused("selected.Dockerfile bytes differ from the accepted build context")
    if (
        s.get("baseline_measurement", {}).get("report_sha256") != EXPECTED_BASELINE_REPORT_SHA256
        or s.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256
    ):
        raise Refused("selection baseline report / archive hashes differ from accepted values")
    return {
        "destination": destination,
        "status": s["status"],
        "pi_attempt": pi,
        "optimized_gain_claimed": False,
        "fresh_revalidation": fr,
    }


def validate_bundle(b: Bundle) -> dict:
    report = {
        "config_digest": digest_of(b.config),
        "manifest_digest": digest_of(b.manifest),
        "index_digest": digest_of(b.index),
        "base_manifest_digest": digest_of(b.base_manifest),
    }
    if report["config_digest"] != EXPECTED_CONFIG:
        raise Refused("raw config bytes do not hash to the accepted config digest")
    if report["manifest_digest"] != EXPECTED_MANIFEST:
        raise Refused("raw platform manifest bytes do not hash to the accepted manifest digest")
    if report["index_digest"] != EXPECTED_INDEX:
        raise Refused("raw index bytes do not hash to the accepted index digest")
    if report["base_manifest_digest"] != EXPECTED_BASE_MANIFEST:
        raise Refused("base manifest bytes do not hash to the pinned public base digest")
    report.update(validate_structure(b.config, b.manifest, b.index, b.base_manifest, b.dockerfile))
    report["selection"] = validate_selection(b.selection, b.dockerfile)
    report["selection_sha256"] = b.selection_sha256
    return report


class RegistryClient(Protocol):
    def blob_exists(self, repo: str, digest: str) -> bool: ...
    def copy_blob(self, src_repo: str, dst_repo: str, digest: str, size: int) -> None: ...
    def put_blob(self, repo: str, data: bytes, digest: str) -> None: ...
    def put_manifest(self, repo: str, data: bytes, media_type: str, reference: str) -> None: ...
    def head_manifest(self, repo: str, reference: str) -> str: ...


class RegctlClient:
    """Thin wrapper over a pinned regctl binary (stream copies; nothing is unpacked)."""

    def __init__(self, binary: Path) -> None:
        binary = binary.absolute()
        data = _load(binary, 16 * 1024**2)
        if sha256_hex(data) != REGCTL_SHA256:
            raise Refused(f"regctl binary sha256 {sha256_hex(data)} != pinned {REGCTL_SHA256}")
        self.bin = str(binary)

    def _run(self, *args: str, stdin: bytes | None = None, allow_absent: bool = False) -> str:
        if not hasattr(self, "end"):
            self.end = time.monotonic() + 1200
        left = self.end - time.monotonic()
        if left <= 0:
            raise Refused("whole publication deadline exhausted")
        with (
            tempfile.TemporaryFile() as out,
            tempfile.TemporaryFile() as err,
            tempfile.TemporaryFile() as input_file,
        ):
            if stdin is not None:
                if len(stdin) > MAX_METADATA_BYTES:
                    raise Refused("bounded registry stdin required")
                input_file.write(stdin)
                input_file.seek(0)
            proc = subprocess.Popen(
                [self.bin, *args],
                stdin=input_file if stdin is not None else subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=(os.name == "posix"),
            )
            try:
                end = min(self.end, time.monotonic() + 600)
                while proc.poll() is None:
                    if time.monotonic() >= end:
                        raise Refused("bounded registry command deadline exhausted")
                    if (
                        os.fstat(out.fileno()).st_size > 1024**2
                        or os.fstat(err.fileno()).st_size > 1024**2
                    ):
                        raise Refused("registry command output bound exceeded")
                    time.sleep(0.02)
                if (
                    os.fstat(out.fileno()).st_size > 1024**2
                    or os.fstat(err.fileno()).st_size > 1024**2
                ):
                    raise Refused("registry command output bound exceeded")
                out.seek(0)
                err.seek(0)
                stdout, stderr = out.read(1024**2), err.read(1024**2)
                if proc.returncode:
                    if allow_absent and re.search(rb"\b404\b|not found|notfound", stderr.lower()):
                        return "ABSENT"
                    # Do not leak credentials or signed download query strings from client stderr.
                    raise Refused(
                        f"registry command failed rc={proc.returncode}; "
                        f"stderr_sha256={sha256_hex(stderr)}"
                    )
                return stdout.decode("utf-8", "strict").strip()
            finally:
                if proc.poll() is None:
                    if os.name == "posix":
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        proc.kill()  # The pinned Go client has no delegated child command.
                proc.wait(timeout=5)

    def blob_exists(self, repo: str, digest: str) -> bool:
        return self._run("blob", "head", repo, digest, allow_absent=True) != "ABSENT"

    def copy_blob(self, src_repo: str, dst_repo: str, digest: str, size: int) -> None:
        self._run("blob", "copy", src_repo, dst_repo, digest)

    def put_blob(self, repo: str, data: bytes, digest: str) -> None:
        self._run("blob", "put", "--digest", digest, repo, stdin=data)

    def put_manifest(self, repo: str, data: bytes, media_type: str, reference: str) -> None:
        self._run(
            "manifest",
            "put",
            "--content-type",
            media_type,
            f"{repo}:{reference}" if not reference.startswith("sha256:") else f"{repo}@{reference}",
            stdin=data,
        )

    def head_manifest(self, repo: str, reference: str) -> str:
        ref = f"{repo}@{reference}" if reference.startswith("sha256:") else f"{repo}:{reference}"
        result = self._run("manifest", "head", "--format", "{{.GetDescriptor.Digest}}", ref)
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", result):
            raise Refused("registry returned malformed manifest digest")
        return result


def publish(
    b: Bundle,
    client: RegistryClient,
    destination: str = DESTINATION,
    tag: str = PUBLICATION_TAG,
) -> dict:
    """Publish selected platform bytes; the original two-child index is provenance only."""
    if destination != DESTINATION:
        raise Refused("destination differs from the approved exact registry repository")
    validate_bundle(b)
    if tag != PUBLICATION_TAG:
        raise Refused("only the reviewed mutable baseline tag is permitted")
    m = strict_json(b.manifest)
    steps: list[dict] = []
    for layer in m["layers"]:
        if not client.blob_exists(destination, layer["digest"]):
            client.copy_blob(SOURCE_REPO, destination, layer["digest"], layer["size"])
        steps.append({"layer": layer["digest"], "size": layer["size"], "present": True})
    client.put_blob(destination, b.config, EXPECTED_CONFIG)
    client.put_manifest(destination, b.manifest, MT_MANIFEST, EXPECTED_MANIFEST)
    # The original index also references an attestation closure not uploaded here.
    # Publish the selected platform manifest directly; retain the original index as provenance.
    client.put_manifest(destination, b.manifest, MT_MANIFEST, tag)
    got_manifest = client.head_manifest(destination, EXPECTED_MANIFEST)
    got_tag = client.head_manifest(destination, tag)
    if got_manifest != EXPECTED_MANIFEST:
        raise Refused(f"read-back platform manifest digest {got_manifest} != {EXPECTED_MANIFEST}")
    if got_tag != EXPECTED_MANIFEST:
        raise Refused(
            f"read-back tag {tag} digest {got_tag} != {EXPECTED_MANIFEST} "
            "(mutable/mismatched reference refused)"
        )
    return {
        "destination": destination,
        "tag": tag,
        "reference": f"{destination}@{EXPECTED_MANIFEST}",
        "original_local_index": EXPECTED_INDEX,
        "original_index_published": False,
        "tag_is_mutable": True,
        "readback_tag_digest": got_tag,
        "readback_manifest_digest": got_manifest,
        "layers": steps,
    }


def receipt_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            dict(payload, written_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()


class ReceiptAttempt:
    """Reserve final evidence once; retain durable append-only phase records.

    The final JSON is written once through its original exclusive handle. A failed
    final write cannot erase the journal's already-fsynced execution uncertainty.
    Path replacement is refused; a different attempt's file is never opened to write.
    """

    def __init__(self, path: Path, payload: dict) -> None:
        self.path = path.absolute()
        self.journal_path = self.path.with_name(self.path.name + ".attempt.jsonl")
        self.final = self.journal = None
        self.finished = False
        self._check_parent()
        if any(p.exists() or p.is_symlink() for p in (self.path, self.journal_path)):
            raise Refused("receipt or attempt journal already exists; choose fresh evidence paths")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            self.final = os.fdopen(os.open(self.path, flags, 0o600), "wb")
            self.final_identity = self._identity(self.final)
            self.journal = os.fdopen(os.open(self.journal_path, flags | os.O_APPEND, 0o600), "ab")
            self.journal_identity = self._identity(self.journal)
            self.record("ATTEMPT_RESERVED", payload)
            if os.name == "posix":
                directory = os.open(
                    self.path.parent, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
                )
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        except BaseException:
            self.close()
            raise  # Preserve any exclusive partial files; never reuse/remove evidence.

    def _check_parent(self) -> None:
        if not self.path.parent.is_dir() or any(
            p.is_symlink() for p in (self.path, self.journal_path, *self.path.parents)
        ):
            raise Refused("receipt requires an existing nonredirected parent")

    @staticmethod
    def _identity(file) -> tuple[int, int]:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise Refused("ordinary evidence file required")
        return info.st_dev, info.st_ino

    def check_owned(self) -> None:
        self._check_parent()
        for path, file, identity in (
            (self.path, self.final, self.final_identity),
            (self.journal_path, self.journal, self.journal_identity),
        ):
            current = path.stat()
            if (current.st_dev, current.st_ino) != identity or self._identity(file) != identity:
                raise Refused("owned receipt/attempt journal identity changed")

    def record(self, event: str, payload: dict) -> None:
        self.check_owned()
        raw = receipt_bytes(dict(payload, event=event))
        # One ordinary JSON object per line; existing complete entries survive an
        # interrupted tail. No untrusted stderr, auth data or client headers enter it.
        self.journal.write(json.dumps(json.loads(raw), sort_keys=True).encode() + b"\n")
        self.journal.flush()
        os.fsync(self.journal.fileno())
        self.check_owned()

    def _write_final(self, raw: bytes) -> None:
        self.final.write(raw)
        self.final.flush()
        os.fsync(self.final.fileno())

    def finish(self, payload: dict) -> None:
        if self.finished:
            raise Refused("attempt final receipt is single-write")
        self.finished = True
        try:
            self.check_owned()
            raw = receipt_bytes(payload)
            self._write_final(raw)
            self.check_owned()
            self.record("FINAL_RECEIPT_SAVED", dict(payload, receipt_sha256=sha256_hex(raw)))
        except (Refused, OSError, ValueError) as exc:
            try:
                self.record("FINAL_RECEIPT_FAILED", dict(payload, error_type=type(exc).__name__))
            except (Refused, OSError, ValueError):
                pass  # The pre-client execution record remains the uncertainty floor.
            raise

    def close(self) -> None:
        for file in (self.final, self.journal):
            if file is not None:
                try:
                    file.close()
                except OSError:
                    pass  # Already failed evidence remains; close is never a success claim.


def write_receipt(path: Path, payload: dict) -> None:
    attempt = ReceiptAttempt(path, payload)
    try:
        attempt.finish(payload)
    finally:
        attempt.close()


def main(argv: list[str] | None = None, client_factory=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--metadata-dir", required=True, type=Path)
    ap.add_argument("--base-manifest", required=True, type=Path)
    ap.add_argument("--dockerfile", required=True, type=Path)
    ap.add_argument("--selection", required=True, type=Path)
    ap.add_argument("--receipt", required=True, type=Path)
    ap.add_argument(
        "--execute",
        action="store_true",
        help="upload (requires --root-approved-selection-sha256)",
    )
    ap.add_argument("--root-approved-selection-sha256", default=None)
    ap.add_argument("--regctl", type=Path, default=None)
    ap.add_argument("--destination", default=DESTINATION)
    a = ap.parse_args(argv)
    fixture = client_factory is not None
    receipt: dict = {
        "mode": "inspection",
        "publisher": "config-only",
        "destination": a.destination,
        "uploaded": False,
        "fixture": fixture,
        "real_registry_upload": False,
    }
    attempt = None
    try:
        attempt = ReceiptAttempt(a.receipt, receipt)
        if a.destination != DESTINATION:
            raise Refused("destination differs from the approved exact registry repository")
        b = load_bundle(a.metadata_dir, a.base_manifest, a.dockerfile, a.selection)
        receipt["validation"] = validate_bundle(b)
        receipt["result"] = "VALIDATED_NOT_UPLOADED"
        if a.execute:
            if (
                not re.fullmatch(r"[0-9a-f]{64}", a.root_approved_selection_sha256 or "")
                or a.root_approved_selection_sha256 != b.selection_sha256
            ):
                raise Refused(
                    "execute refused: --root-approved-selection-sha256 "
                    "does not match the selection file"
                )
            receipt["mode"] = "execute"
            receipt["result"] = "EXECUTION_IN_PROGRESS"
            receipt["writes_attempted"] = True
            receipt["partial_remote_objects_possible"] = True
            attempt.record("EXECUTION_IN_PROGRESS", receipt)
            if client_factory is not None:
                client = client_factory()
            else:
                if a.regctl is None:
                    raise Refused("execute refused: --regctl pinned binary path required")
                client = RegctlClient(a.regctl)
            attempt.check_owned()
            receipt["publication"] = publish(b, client, a.destination)
            receipt["uploaded"] = not fixture
            receipt["real_registry_upload"] = not fixture
            receipt["result"] = (
                "FIXTURE_VALIDATED_NO_REAL_UPLOAD" if fixture else "UPLOADED_AND_READBACK_VERIFIED"
            )
    except (
        Refused,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.TimeoutExpired,
    ) as e:
        receipt["result"] = "REFUSED"
        receipt["reason"] = str(e)
        try:
            if attempt is not None:
                attempt.finish(receipt)
        except (Refused, OSError):
            pass  # Never overwrite prior evidence even when this attempt is refused.
        finally:
            if attempt is not None:
                attempt.close()
        print(f"REFUSED: {type(e).__name__}: {e}", file=sys.stderr)
        return 65
    try:
        attempt.finish(receipt)
    except (Refused, OSError):
        print(
            "REFUSED: evidence path unavailable; "
            "any attempted remote objects require reconciliation",
            file=sys.stderr,
        )
        return 65
    finally:
        attempt.close()
    print(receipt["result"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
