#!/usr/bin/env bash
# Offline restore/verification for the exact measured LLMD baseline archive.
# 1) verifies every part against SHA256SUMS, 2) verifies the full concatenated
# archive hash, 3) only then (optionally) runs `docker load`. No URL is fetched
# here: download the parts yourself (see README) and run this in that directory.
set -euo pipefail
EXPECTED_ARCHIVE_SHA256='c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47'
EXPECTED_ARCHIVE_BYTES=5923200000
PARTS=(llmd-baseline.docker.tar.part-01 llmd-baseline.docker.tar.part-02 llmd-baseline.docker.tar.part-03 llmd-baseline.docker.tar.part-04)
OUT=llmd-baseline.docker.tar
for p in "${PARTS[@]}"; do [[ -f "$p" ]] || { echo "missing $p" >&2; exit 1; }; done
[[ -f SHA256SUMS ]] || { echo "missing SHA256SUMS" >&2; exit 1; }
echo "verifying parts against SHA256SUMS"
grep -E ' llmd-baseline\.docker\.tar\.part-0[1-4]$' SHA256SUMS | sha256sum -c --strict -
if [[ -e "$OUT" ]]; then echo "refusing to overwrite existing $OUT" >&2; exit 1; fi
echo "concatenating parts -> $OUT"
cat "${PARTS[@]}" > "$OUT.partial"
actual_bytes=$(stat -c %s "$OUT.partial")
actual_sha=$(sha256sum "$OUT.partial" | cut -c1-64)
if [[ "$actual_bytes" != "$EXPECTED_ARCHIVE_BYTES" || "$actual_sha" != "$EXPECTED_ARCHIVE_SHA256" ]]; then
  echo "FULL ARCHIVE MISMATCH: bytes=$actual_bytes sha256=$actual_sha (expected $EXPECTED_ARCHIVE_BYTES / $EXPECTED_ARCHIVE_SHA256)" >&2
  echo "partial retained as $OUT.partial; NOT loading" >&2; exit 1
fi
mv "$OUT.partial" "$OUT"
echo "FULL ARCHIVE VERIFIED: $actual_bytes bytes sha256 $actual_sha"
if [[ "${1:-}" == "--docker-load" ]]; then
  echo "docker load < $OUT"; docker load < "$OUT"
  echo "expected image index sha256:ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540 (platform manifest sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d, config sha256:0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f)"
else
  echo "archive verified; re-run with --docker-load to import it (requires Docker with containerd image store to keep the index identity)"
fi
