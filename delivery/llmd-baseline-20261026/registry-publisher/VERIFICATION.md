# Source verification — 26 October 2026

The publisher overlay passes 40 offline tests on native Linux CPython3.14.4,
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
Both inactive workflow templates select the final JSON and its sibling
`.attempt.jsonl` journal for the `always()` recovery-artifact step. Two added
regressions inject a real receipt final-write failure and check that both the
partial final and the durable journal match the literal artifact paths. This
checks the template contract, not GitHub runner survival or successful artifact
upload; a lost runner or failed upload can still lose evidence.

Workflow templates remain inactive and no publication approval marker is included.

## Actual publication and workflow context fix — 27 October 2026

The first root-layout execution was rejected before any job because `runner.temp`
is unavailable in job-level `env`. The corrected template initializes private
client paths using `$RUNNER_TEMP` inside a step and exports them through
`$GITHUB_ENV`. Publisher, checker, selection, permissions and timeouts are unchanged.
Seven focused workflow contract/recovery tests passed on the corrected template.

Actual run 40596159814 at b56d284 completed successfully in 96 seconds, including
the source-bound approval check, pinned client, package upload, authenticated
manifest/tag read-back, temporary logout and both receipt/journal artifacts.
The 5,472-byte artifact ZIP matches GitHub digest
`c646162bb70abdbec19e98e69ec5dde70ed0e0d9bff1d04c0d7c867ff53d0e23`.
The receipt SHA is `2460705ade08dd055e96155ca29c5ff5d7965b08d72a11e139c3eac65428ab7c`;
the journal SHA is `920ba0f85cf32781756cc1806fa2a2fd9e566abf2c7f1b175e175337a164b41a`.
The journal's final saved-receipt hash matches the actual receipt bytes.

These actual results supplement the historical closed tests above. They do not
recover missing historical inference traces, establish an optimization gain, or
substitute for full anonymous download and Docker engine checks. No execution
marker or active workflow is added to this nested source tree.

The subsequent read-only run 40598808475 passed complete anonymous GET/hash
verification for all 25 objects and 5,923,167,710 bytes in 194.331 seconds. Root
independently checked the artifact ZIP digest, exact raw manifest/config, every
descriptor/body hash/length, retained stderr and final journal-to-receipt hash.
An actual empty-client-config Docker 29.7.1 pull/inspect/CPU-help check also passed;
cached inherited layers are disclosed separately from the full network byte proof.
The owned help container was confirmed absent. See `PUBLICATION_STATUS.md` for
public run links, immutable reference and receipt digests. These close publication
and anonymous baseline image access, while GPU inference and genuine optimization
remain separate tasks.
