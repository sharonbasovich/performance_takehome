# Source verification — 26 October 2026

The publisher overlay now passes 38 offline tests on native Linux CPython3.14.4,
with zero skips. Windows CPython3.13.3 passes the same suite with two explicitly
POSIX-only cases skipped (relative executable launch and replacing an open receipt).
The original 29 tests continue to pass. Locked Ruff0.16.10 root lint and overlay
source/test format-check pass under the repository's existing configuration. A
read-only full-root format-check flags 14 unchanged starter/protected files; the same
failures were reproduced from frozen `e833fcad` Git blobs. Those files were not edited.
Default real CLI
inspection returned `VALIDATED_NOT_UPLOADED`; no registry client was invoked.

Nine added lifecycle regressions cover the checked relative executable with PATH
excluding cwd, unavailable receipt parent/write access, sync failure before client
construction, durable execution records and stable receipt identity, prior journal
preservation, replacement refusal, partial final-write uncertainty and constructor
failure. The two reported bugs were independently reproduced against frozen
`e833fcad` source before the fix. All registry operations in these checks are closed
fakes; no real registry operation was performed.

Independent review checked the exact small OCI metadata, missing-attestation
closure, platform selection, strict destination/schema, workflow source gates and
exclusive/uncertain failure receipts. The final integration adds repository-style
formatting and exception chaining, qualified package-existence wording and local
Git attributes preserving raw image/selection bytes and LF source on Windows.
Earlier sealed source, failed probes and review receipts remain separate provenance.

These results exercise a closed fake registry and bounded local Python children.
They do not verify owner settings, package entitlement/visibility, large-layer
transfer, media acceptance, anonymous pull, inference, optimization or billing.
Workflow templates remain inactive and no publication approval marker is included.
