# Exact measured LLMD baseline image

This directory preserves the exact metadata and tar structure of a real, verified LLMD image export. The selected image was freshly revalidated on one MI355X using Qwen3.6-27B: all 30 requests matched the complete baseline and passed usage/finish gates. It is a baseline, with no optimization gain claimed. The genuine Pi attempt failed at an upstream response deadline before producing a patch; that remains an unfinished optimization result.

The complete original archive is **5,923,200,000 bytes**, SHA-256 `c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47`. Its selected platform manifest is `sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d`; its Docker image-index identity is `sha256:ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540`. These identify different objects and are intentionally distinguished.

All 23 filesystem blobs are inherited unchanged from the public pinned base `docker.io/zmlai/llmd@sha256:0a2cd01a2e53c78934a8cfef66f8668da7666be4954a5d18b72df089c54ea34f`. Only image configuration and build metadata differ. Model weights are outside the image. Upstream engine/source/license provenance is inherited; this does not label the entire image Apache-2.0 or claim a bit-reproducible Docker rebuild.

`segments/` preserves every other archive byte, including original headers, metadata, padding and suffix. `reconstruction-manifest.json` specifies the complete ordered byte coverage. Its SHA-256 is `da39f7f6ec2fec5bb6ef4c42ed34b62867d69f01bfece904e5ac62e531776b5c`. Fetch each public layer from `docker.io/zmlai/llmd` by the exact digest in the manifest, storing it under its 64-character SHA in a local blob directory, without unpacking it. The offline utility then verifies every input, joins exact bytes and checks the complete original archive hash:

```sh
python reconstruct_exact_archive.py --execute-reviewed \
  --metadata-dir /absolute/path/to/this-directory \
  --blob-dir /absolute/path/to/verified-public-blobs \
  --output /absolute/path/to/llmd-baseline.docker.tar \
  --manifest-sha256 da39f7f6ec2fec5bb6ef4c42ed34b62867d69f01bfece904e5ac62e531776b5c
```

The utility performs no network access, Docker operation or rebuild. It refuses overwrite and only publishes a complete output after its exact original hash matches. `original-receipt.json` records the actual export's full layer/decompression verification; the metadata audit alone did not read all layer bytes. Raw configuration was reviewed: its environment is exactly inherited from the public base, with no user/provider credentials added.

## Public release delivery (verified)

The exact archive was reconstructed from anonymously fetched public base blobs (all 23 digests/sizes verified), hash-verified (`c759f7c2…`, 5,923,200,000 bytes) and published as GitHub release assets, split into four parts below GitHub's documented 2 GiB per-asset limit ([GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)):

- Release: <https://github.com/sharonbasovich/performance_takehome/releases/tag/task2-llmd-baseline-20261026> (release id `424055820`, target commit `ff3f2880caa25bd01a7cb7177382e298f93d9760`)
- Parts (each 1,480,800,000 bytes): `part-01` `47ad0aa2e44ee9ebadd4e4cc96afd7e20fbf7e010206e126ecd2ecf1a5f7c973` (asset 677669094), `part-02` `5f9c4bc23ec3be010e72a4688269cde49898016b187ae6f9b74bcdeb50e27dad` (677669124), `part-03` `7bd5e0bc9c395cf8dbd2d0cd885cc2a59efe3df78d5f4ed1eb2c2cd91944cc5f` (677669137), `part-04` `164aaac821e1f9cb9591794996a867916fffce4c1bede32c1e2741862d6336ce` (677669128); `cat part-01..04` = `c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47`.
- `RELEASE_SHA256SUMS` here equals the uploaded `SHA256SUMS` asset.
- Restore-helper versions on the release (all retained; none replaced):
  - `restore_llmd_baseline.sh` (asset 677669095, SHA-256 `0e32d498…`) — **v1, deprecated provenance**: re-run `--docker-load` always rejected an existing output, overwrote an existing `.partial`, its `grep` could accept an incomplete part list, and it could not verify an already-assembled archive.
  - `restore_llmd_baseline_v2.sh` (asset 677751514, SHA-256 `2ffef91e…`) — **v2, superseded provenance**: Greptile review discussion 4376052507 (on commit 2faaeb1c) found that a directory, or symlink to one, appearing at the output path during assembly made `ln` place the archive inside it and lose the documented partial.
  - **`restore_llmd_baseline_v2_1.sh`** (asset 677786560, 6,474 bytes, SHA-256 `d297276046133930dcaee522f24ddf11126eef8cf23e7ab23fbf4456d3463209`, checksum asset 677786558) — **current**: byte-identical to Git `restore_llmd_baseline_v2.sh` at commit `ad665d35439d4b1815c0bdb0791eaeadec7172f5`, which fixes the race with `ln -T --` and adds directory/symlink regressions. Anonymously re-downloaded and compared byte-for-byte with the Git blob.
- `restore_llmd_baseline_v2.sh` in this directory is the supported offline helper (strict subcommands, pinned hashes, exclusive creation, no clobbering of files or symlinks, failed partials preserved, `docker load` only after a full verified hash). `test_restore_llmd_baseline_v2.py` holds synthetic CPU tests that patch a copied fixture; the production constants are asserted unchanged. At `ad665d35` all 12 offline tests (4 reconstruction + 8 restore) pass and ruff 0.16.10 `check` and `format --check` pass on the three Python files.

```sh
# in a directory holding the four parts (+ optional SHA256SUMS):
bash restore_llmd_baseline_v2.sh verify-parts                    # every part: size + pinned SHA-256
bash restore_llmd_baseline_v2.sh assemble                        # exclusive .partial -> llmd-baseline.docker.tar, full hash checked
bash restore_llmd_baseline_v2.sh verify-archive                  # re-verify an existing archive (never modifies it)
bash restore_llmd_baseline_v2.sh docker-load                     # verify-archive, then `docker load -i`; prints expected identities
# --dir DIR selects the asset directory; --output FILE selects the archive path. Unknown arguments exit 64.
python3 -B -m unittest -v test_reconstruct_exact_archive test_restore_llmd_baseline_v2   # 12 offline tests, no network/Docker/real archive
```

- Independent full-archive check: a separate reviewer anonymously streamed all 5,923,200,000 release bytes (2026-10-26 09:53:54–10:05:04Z); all four part hashes, the concatenation `c759f7c2…` and the four small assets passed. No payload was saved and no Docker load was part of that check.
- CPU import: `IMPORT_RECEIPT.md` records the one actual `docker load` of the verified archive (Docker 29.7.2, containerd image store, loaded image ID `sha256:ccd73fc2…`, `/llmd/llmd --help` exit 0 with `--network none`), with raw-log hashes; no inference, weights or GPU.
- Anonymous verification (no Authorization header) after publishing: release API and all eight assets fetched, every part hash and the streamed ordered concatenation matched `c759f7c2…`; see `evidence.json` (`public_delivery`).

Limits: this is release-asset delivery only. Registry (GHCR) publication and anonymous `docker pull` remain separate, unverified checks and are not claimed. Loading the archive reproduces the image-index identity `ccd73fc2…` only on Docker's containerd image store.
