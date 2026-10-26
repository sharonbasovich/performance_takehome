#!/usr/bin/env bash
# restore_llmd_baseline_v2.sh - strict offline verify/assemble/load for the exact
# measured LLMD baseline archive (release task2-llmd-baseline-20261026).
#
#   restore_llmd_baseline_v2.sh verify-parts   [--dir DIR]
#   restore_llmd_baseline_v2.sh assemble       [--dir DIR] [--output FILE]
#   restore_llmd_baseline_v2.sh verify-archive [--output FILE]
#   restore_llmd_baseline_v2.sh docker-load    [--output FILE]
#
# DIR defaults to the current directory, FILE to DIR/llmd-baseline.docker.tar.
# Every expected part is checked against the hashes PINNED BELOW (SHA256SUMS is
# only cross-checked when present). assemble creates FILE exclusively through a
# .partial file; it never overwrites, follows or replaces an existing path or
# symlink, and keeps a failed partial under a timestamped .failed name.
# verify-archive accepts an existing FILE only when size and SHA-256 match exactly.
# docker-load performs verify-archive first and runs `docker load` only on PASS.
# The script fetches nothing and never interpolates URLs.
set -euo pipefail

ARCHIVE_SHA256='c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47'
ARCHIVE_BYTES=5923200000
PART_BYTES=1480800000
PART_NAMES=(llmd-baseline.docker.tar.part-01 llmd-baseline.docker.tar.part-02 llmd-baseline.docker.tar.part-03 llmd-baseline.docker.tar.part-04)
PART_SHA256=(
  47ad0aa2e44ee9ebadd4e4cc96afd7e20fbf7e010206e126ecd2ecf1a5f7c973
  5f9c4bc23ec3be010e72a4688269cde49898016b187ae6f9b74bcdeb50e27dad
  7bd5e0bc9c395cf8dbd2d0cd885cc2a59efe3df78d5f4ed1eb2c2cd91944cc5f
  164aaac821e1f9cb9591794996a867916fffce4c1bede32c1e2741862d6336ce
)
EXPECTED_INDEX='sha256:ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540'
EXPECTED_MANIFEST='sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d'
EXPECTED_CONFIG='sha256:0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f'

EX_USAGE=64; EX_DATAERR=65; EX_NOINPUT=66; EX_CANTCREAT=73

usage() { sed -n '2,17p' "$0" >&2; exit "$EX_USAGE"; }
fail() { echo "FAIL: $*" >&2; exit "$EX_DATAERR"; }
sha_of() { sha256sum -- "$1" | cut -c1-64; }
size_of() { stat -c %s -- "$1"; }
regular_file() { [[ ! -L "$1" && -f "$1" ]]; }
path_absent() { [[ ! -e "$1" && ! -L "$1" ]]; }

verify_parts() {
  local dir=$1 i name path
  for i in "${!PART_NAMES[@]}"; do
    name=${PART_NAMES[$i]}; path="$dir/$name"
    regular_file "$path" || { echo "FAIL: missing or non-regular part $path" >&2; exit "$EX_NOINPUT"; }
    [[ $(size_of "$path") == "$PART_BYTES" ]] || fail "size mismatch $name: $(size_of "$path") != $PART_BYTES"
    [[ $(sha_of "$path") == "${PART_SHA256[$i]}" ]] || fail "sha256 mismatch $name"
    echo "OK part $name $PART_BYTES bytes ${PART_SHA256[$i]}"
  done
  if [[ -e "$dir/SHA256SUMS" ]]; then
    regular_file "$dir/SHA256SUMS" || fail "SHA256SUMS is not a regular file"
    for i in "${!PART_NAMES[@]}"; do
      grep -qxF "${PART_SHA256[$i]}  ${PART_NAMES[$i]}" "$dir/SHA256SUMS" || fail "SHA256SUMS disagrees with pinned hash for ${PART_NAMES[$i]}"
    done
    grep -qxF "$ARCHIVE_SHA256  llmd-baseline.docker.tar" "$dir/SHA256SUMS" || fail "SHA256SUMS disagrees with pinned archive hash"
    echo "OK SHA256SUMS consistent with pinned hashes"
  fi
  echo "PASS all ${#PART_NAMES[@]} parts verified against pinned hashes"
}

verify_archive() {
  local out=$1 size sha
  regular_file "$out" || { echo "FAIL: archive $out missing or not a regular file" >&2; exit "$EX_NOINPUT"; }
  size=$(size_of "$out"); sha=$(sha_of "$out")
  [[ $size == "$ARCHIVE_BYTES" && $sha == "$ARCHIVE_SHA256" ]] || fail "archive mismatch: bytes=$size sha256=$sha (expected $ARCHIVE_BYTES / $ARCHIVE_SHA256); file left untouched"
  echo "PASS archive $out $size bytes sha256 $sha"
}

assemble() {
  local dir=$1 out=$2 partial="$2.partial" name p
  verify_parts "$dir"
  path_absent "$out" || { echo "FAIL: refusing to clobber existing path $out (verify it with verify-archive)" >&2; exit "$EX_CANTCREAT"; }
  path_absent "$partial" || { echo "FAIL: refusing to clobber existing path $partial" >&2; exit "$EX_CANTCREAT"; }
  [[ -d $(dirname -- "$out") && ! -L $(dirname -- "$out") ]] || { echo "FAIL: output directory must be a real directory" >&2; exit "$EX_CANTCREAT"; }
  ( set -o noclobber; : > "$partial" ) || { echo "FAIL: exclusive creation of $partial failed" >&2; exit "$EX_CANTCREAT"; }
  regular_file "$partial" || { echo "FAIL: $partial is not a regular file after creation" >&2; exit "$EX_CANTCREAT"; }
  for name in "${PART_NAMES[@]}"; do cat -- "$dir/$name" >> "$partial"; done
  sync -- "$partial"
  if [[ $(size_of "$partial") != "$ARCHIVE_BYTES" || $(sha_of "$partial") != "$ARCHIVE_SHA256" ]]; then
    p="$partial.failed-$(date -u +%Y%m%dT%H%M%SZ)"
    while ! path_absent "$p"; do p="$p.1"; done
    mv -n -- "$partial" "$p"
    fail "assembled bytes do not match pinned archive; failed partial preserved at $p"
  fi
  ln -T -- "$partial" "$out" || { echo "FAIL: $out appeared during assembly; partial kept at $partial" >&2; exit "$EX_CANTCREAT"; }
  rm -f -- "$partial"
  verify_archive "$out"
}

docker_load() {
  local out=$1 id
  verify_archive "$out"
  command -v docker >/dev/null || { echo "FAIL: docker not found; archive verified, nothing loaded" >&2; exit "$EX_NOINPUT"; }
  echo "docker load -i $out"
  docker load -i "$out"
  echo "expected identities: index $EXPECTED_INDEX manifest $EXPECTED_MANIFEST config $EXPECTED_CONFIG"
  echo "containerd image store keeps the index identity; classic graphdriver stores report the config digest as image ID"
  for id in "${EXPECTED_INDEX#sha256:}" "${EXPECTED_CONFIG#sha256:}"; do
    docker image inspect --format 'loaded image id={{.Id}} repo-digests={{json .RepoDigests}}' "$id" 2>/dev/null && return 0
  done
  echo 'WARN: neither expected image id is inspectable; check "docker images --digests" manually' >&2
}

main() {
  [[ $# -ge 1 ]] || usage
  local cmd=$1 dir=. out=; shift
  while [[ $# -gt 0 ]]; do
    case $1 in
      --dir) [[ $# -ge 2 ]] || usage; dir=$2; shift 2 ;;
      --output) [[ $# -ge 2 ]] || usage; out=$2; shift 2 ;;
      *) usage ;;
    esac
  done
  [[ -d $dir ]] || { echo "FAIL: --dir $dir is not a directory" >&2; exit "$EX_NOINPUT"; }
  [[ -n $out ]] || out="$dir/llmd-baseline.docker.tar"
  case $cmd in
    verify-parts) verify_parts "$dir" ;;
    assemble) assemble "$dir" "$out" ;;
    verify-archive) verify_archive "$out" ;;
    docker-load) docker_load "$out" ;;
    *) usage ;;
  esac
}
main "$@"
