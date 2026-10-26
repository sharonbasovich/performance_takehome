# Inactive registry publisher source

This supplements the verified [baseline release](https://github.com/sharonbasovich/performance_takehome/releases/tag/task2-llmd-baseline-20261026).
No registry upload, installed workflow, public package or anonymous Docker pull has
been verified. The selected image is the unchanged measured baseline: genuine Pi
failed before a patch; no optimization gain is claimed. Its fresh revalidation PASS
receipt/hash survives, but the full fresh report and30traces were not exported.

The intended registry identity is the existing platform manifest:

`ghcr.io/sharonbasovich/performance_takehome-task2-llmd@sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d`

Publication and access at this reference are **unverified**; this work performed no
registry upload. The platform/config/23layer bytes remain exact.
The original archive index `ccd73fc2…` has a second attestation child, whose closure
this publisher does not transfer. It retains that index as provenance and publishes
the platform directly. The tag `baseline-ccd73fc2` is mutable; use the digest as identity.
The schema2selection binds the platform target and preserves the superseded selection
as explicit legacy evidence. Model weights remain outside the image.

## Offline inspection and tests

From this directory, with Python3.11+:

On Windows, use a short checkout path or Git's `core.longpaths=true` setting; a
deep parent directory can exceed Git's legacy filename limit. Candidate-local
attributes preserve exact raw metadata and selection bytes and force source LF
even when `core.autocrlf=true`.

```sh
python -B src/publish_baseline_config_only.py \
  --metadata-dir delivery/metadata --base-manifest delivery/base-manifest.json \
  --dockerfile delivery/selected.Dockerfile --selection evidence/selection.json \
  --receipt /absolute/existing/directory/new-inspection-receipt.json
python -B -m unittest discover -s tests -v
```

Inspection performs no network or registry-client invocation. Use a fresh receipt
path and its sibling `<receipt>.attempt.jsonl`; previous evidence is never overwritten.
The publisher exclusively opens the final receipt and append-only journal and syncs
the reserved state before constructing any registry client. It records and syncs
`EXECUTION_IN_PROGRESS`, including possible partial remote objects, before client
construction. The final JSON contract remains unchanged and is written once through
the original owned handle; a replaced receipt path is refused. The journal records
the saved receipt's hash or a final-write failure when possible.

An interrupted attempt can leave an empty/partial final receipt or an incomplete
journal tail. Retain both files; complete earlier journal entries remain evidence.
After an execution-start record, failure, missing final bytes or `uploaded=false`
does not mean zero remote writes or cancellation. Reconcile remote state before a
new attempt, using fresh evidence paths. File writes are fsynced, and POSIX directory
entries are synced on reservation; crash durability still depends on the OS,
filesystem and storage. Windows does not provide the POSIX directory-sync step here.
Hard loss or later storage failure cannot guarantee a complete final receipt.

Tests use the exact small public
metadata and a closed fake registry, plus bounded owned local Python children for
timeout/output checks. Fake receipts explicitly distinguish fixtures from uploads.
No6GBdownload, Docker daemon, GPU, model or credential is needed.

The publisher checks exact source/model/image/entrypoint/layer/selection identities,
strict bounded JSON, destination allowlist and exclusive evidence. A pinned regctl
client can later stream inherited blobs without Docker unpacking. Its v0.11.7 SHA256
pin is self-computed, not an official checksum/signature attestation. The checked
binary's absolute path is also its launch path, including when supplied as `./regctl`;
launch does not search PATH for a different executable. Timeouts may
leave partial remote objects, requiring reconciliation; failure is never a zero-write
or cancellation claim. Output-size monitoring can overshoot between polls.

## Staged templates and remaining owner actions

`workflow/` holds inert reviewed templates. They are deliberately outside `.github/`.
**This nested source location is not the templates' execution layout.** They expect a
separately reviewed repository-root `registry-publisher/` tree; the approval checker
also binds the installed workflow under that root's sibling `.github/workflows/`.
Moving/installing them or adapting those paths requires an explicit deployment review.
Keep protected assessment infrastructure unchanged. No approval marker is supplied;
`SOURCE_PINS.json` records source identity and grants no execution approval.

1. Verify existing owner Actions/settings and registry/package rights. Earlier
   evidence only inferred disabled fork workflows; settings could not be read.
2. On a separately reviewed publication branch/layout, inspect with the read-only
   exact inspection-branch template first. It neither logs in nor uploads.
3. Actual execution requires the exact approved publication branch and a source-bound
   marker checked before registry login. It uses an ephemeral job token through
   environment/stdin. Ordinary PR pushes and missing markers cannot authorize upload.
4. Verify large-layer timeout/media acceptance, exact read-back and organizer access
   or package visibility; then independently verify all blobs and anonymously pull
   the immutable platform digest. A private package is not anonymously accessible.

Existing entitlement/pricing, package rights, large zstd transfer and visibility remain
unproved. No new credential, broader scope, terms, merge or paid overage is authorized
by this source packet. These checks are not an official grade or successful optimization.
