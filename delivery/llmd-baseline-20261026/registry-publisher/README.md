# Registry publisher source

This supplements the verified [baseline release](https://github.com/sharonbasovich/performance_takehome/releases/tag/task2-llmd-baseline-20261026).
The separately reviewed repository-root deployment published the exact baseline
platform image in [GitHub Actions run 40596159814](https://github.com/sharonbasovich/performance_takehome/actions/runs/40596159814).
The job used temporary package-write access, verified authenticated digest/tag
read-back, uploaded both evidence files and logged out. The owner package page
shows Public. Complete anonymous blob verification and Docker pull also passed;
see [publication status](PUBLICATION_STATUS.md).

This nested source remains an inert template: it installs no workflow or approval
marker. The selected image is the unchanged measured baseline: genuine Pi failed
before a patch; no optimization gain is claimed. The historical fresh revalidation
PASS receipt/hash survives, but the full fresh report and 30 traces were not exported.

The intended registry identity is the existing platform manifest:

`ghcr.io/sharonbasovich/performance_takehome-task2-llmd@sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d`

Publication, authenticated read-back and complete anonymous access at this reference
are verified. The platform/config/23 layer bytes remain exact.
The original archive index `ccd73fc2…` has a second attestation child, whose closure
this publisher does not transfer. It retains that index as provenance and publishes
the platform directly. The tag `baseline-ccd73fc2` is mutable; use the digest as identity.
The frozen `evidence/selection.json` retains its pre-publication status for source
provenance. The independently verified current status is `PUBLICATION_STATUS.md`.
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

1. Existing owner Actions/settings were read without changes. The default token
   remains read-only; the designated publication job alone requests package write.
2. The read-only exact inspection passed in run 40578387168; its receipt/journal
   bytes were independently verified before publication.
3. Actual publication passed on the separately reviewed approved branch at b56d284.
   Its source-bound marker was checked before login and its temporary token logged
   out. Ordinary PR pushes and missing markers still cannot authorize upload.
4. Independent anonymous full-blob verification passed in run 40598808475, followed
   by an empty-client-config Docker 29.7.1 pull, image inspection and CPU help check.
   The byte proof downloaded every body independently; Docker reused cached base
   layers. These checks do not establish fresh GPU inference or an optimization gain.

Actual publication establishes this job's package-write entitlement, large zstd
transfer and authenticated digest read-back. Anonymous full-body access and a
Docker pull/CPU help check passed separately. No new credential, broader scope, terms, merge or paid overage is authorized
by this source packet. These checks are not an official grade or successful optimization.
