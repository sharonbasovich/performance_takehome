"""Offline byte-exact reconstruction; default does no I/O and writes nothing.

Public compressed blobs must already exist locally, named by their SHA-256.
This utility performs no network, registry, Docker, credential or GPU operation.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

MANIFEST_SHA = "da39f7f6ec2fec5bb6ef4c42ed34b62867d69f01bfece904e5ac62e531776b5c"
ARCHIVE_SHA = "c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47"
ARCHIVE_BYTES = 5923200000
RECEIPT_SHA = "ae7771fef2079f163856be33ac23f2914830dc038c00501d9a4b6409d045c55a"


def require(test, message):
    if not test:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def plain(path):
    require(
        path.is_absolute() and not any(p.is_symlink() for p in [path, *path.parents]),
        "nonredirected absolute input required",
    )
    require(path.is_file(), "regular source file required")
    return path


def validate_manifest(data):
    require(
        data["archive_bytes"] == ARCHIVE_BYTES
        and data["archive_sha256_from_pinned_original_receipt"] == ARCHIVE_SHA,
        "original archive identity differs",
    )
    require(
        data["original_receipt_sha256"] == RECEIPT_SHA and data["layer_count"] == 23,
        "original receipt/layer count differs",
    )
    cursor = 0
    layers = []
    for segment in data["segments"]:
        require(
            type(segment["offset"]) is int
            and segment["offset"] == cursor
            and type(segment["bytes"]) is int
            and segment["bytes"] > 0,
            "complete nonoverlapping exact byte coverage required",
        )
        require(
            re.fullmatch("[0-9a-f]{64}", segment["sha256"]) is not None,
            "exact payload digest required",
        )
        require(
            segment["kind"] in {"exact_export_bytes", "public_base_compressed_blob"},
            "unknown reconstruction segment",
        )
        if segment["kind"] == "public_base_compressed_blob":
            layers.append(segment)
        else:
            require(
                re.fullmatch(r"segments/[0-9]{3}\.bin", segment["file"]) is not None,
                "private segment path differs",
            )
        cursor += segment["bytes"]
    require(cursor == ARCHIVE_BYTES and len(layers) == 23, "archive coverage/layer count differs")
    return layers


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-reviewed", action="store_true")
    parser.add_argument("--metadata-dir", type=Path)
    parser.add_argument("--blob-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    if not args.execute_reviewed:
        print(
            json.dumps({"inactive": True, "state_reads": 0, "archive_writes": 0, "network": False})
        )
        return 0
    require(
        args.manifest_sha256 == MANIFEST_SHA,
        "independently reviewed exact reconstruction manifest pin required",
    )
    require(
        all(
            p is not None and p.is_absolute()
            for p in [args.metadata_dir, args.blob_dir, args.output]
        ),
        "explicit absolute paths required",
    )
    manifest = plain(args.metadata_dir / "reconstruction-manifest.json")
    require(digest(manifest) == MANIFEST_SHA, "saved manifest bytes changed")
    data = json.loads(manifest.read_bytes())
    validate_manifest(data)
    require(
        digest(plain(args.metadata_dir / "original-receipt.json")) == RECEIPT_SHA,
        "original receipt changed",
    )
    inputs = []
    for segment in data["segments"]:
        path = (
            (args.metadata_dir / segment["file"])
            if segment["kind"] == "exact_export_bytes"
            else args.blob_dir / segment["sha256"]
        )
        plain(path)
        require(path.stat().st_size == segment["bytes"], "source size differs")
        # Validate every public compressed blob against its exact OCI digest.
        require(digest(path) == segment["sha256"], "source digest differs")
        inputs.append(
            (segment, path, path.stat().st_dev, path.stat().st_ino, path.stat().st_mtime_ns)
        )
    partial = args.output.with_name(args.output.name + ".reconstruct.partial")
    require(
        not args.output.exists()
        and not args.output.is_symlink()
        and not partial.exists()
        and not partial.is_symlink(),
        "never overwrite original/output/partial",
    )
    require(
        not any(p.is_symlink() for p in [args.output.parent, *args.output.parent.parents]),
        "nonredirected output parent required",
    )
    result_hash = hashlib.sha256()
    written = 0
    with partial.open("xb") as target:
        for segment, path, dev, ino, mtime in inputs:
            st = path.stat()
            require(
                (st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size)
                == (dev, ino, mtime, segment["bytes"]),
                "source changed after validation",
            )
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1 << 20), b""):
                    target.write(block)
                    result_hash.update(block)
                    written += len(block)
            st = path.stat()
            require(
                (st.st_dev, st.st_ino, st.st_mtime_ns) == (dev, ino, mtime),
                "source changed during copy",
            )
        target.flush()
        os.fsync(target.fileno())
    require(
        written == ARCHIVE_BYTES and result_hash.hexdigest() == ARCHIVE_SHA,
        "reconstruction mismatch: retain partial, never claim full completion",
    )
    # Hardlink fails if another complete output appeared; retain partial on error.
    os.link(partial, args.output)
    partial.unlink()
    print(
        json.dumps(
            {
                "status": "BYTE_IDENTICAL_ARCHIVE_RECONSTRUCTED_AND_HASH_VERIFIED",
                "archive_bytes": written,
                "archive_sha256": result_hash.hexdigest(),
                "original_receipt_sha256": RECEIPT_SHA,
                "docker_load_or_publication": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
