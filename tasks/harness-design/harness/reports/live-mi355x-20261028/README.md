# 28 October Task 2 public evidence

This packet supports a genuine stock Pi proposal, an exact one-knob candidate
build, a failed candidate startup, reversion to the baseline, and a fresh final
baseline measurement. It claims no speedup and no official grade.

The later [measured Pi2 feedback cycle](pi2-measured/README.md) adds 90 actual
control/candidate/final requests, all passing, with a no_change decision. The
baseline remains selected. The first cycle and its failed candidate are preserved.

The selected immutable reference is
`ghcr.io/sharonbasovich/performance_takehome-task2-llmd@sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d`.
The rejected candidate is platform manifest
`sha256:ab62d880b43412b895dbc1abc25a7eb092f954df40b0f72c896e5ea5bbbee5dd`
with config `sha256:ed53dd105fa9bc76c1db8ad8261f8cfc435de4e03684b08931025261ff5670de`.
The two identities are kept separate; the candidate was not published as a winner.

## Files and attribution

- `baseline/`, `control/`, `selected-final/`: exact full reports, samples, result
  receipts, and 31-line durable trace files (one startup probe plus 30 measured
  requests). `baseline/golden.json` holds six outputs established by the baseline.
- `candidate/`: startup-failure receipt, container logs, and an empty request trace
  file. There is deliberately no candidate performance report.
- `pi/`: exact proposal, Dockerfile and exit receipt; sanitized runtime inventory
  and tool-event metadata. Only event names, call IDs, sequence numbers,
  restrictive work-filename metadata, argument byte counts/hashes, stop reasons,
  and selected runtime/artifact hashes are retained from the private transcript.
- `candidate-build/`, `candidate-metadata/`: actual guard result, build arguments,
  Docker image inspection, build logs, and exact small OCI manifest/config bytes.
  Config includes inherited public-image telemetry environment entries; it does
  not contain a human's provider or registry credentials.
- `actual-source/`: exact canonical source at
  `99c006dfeb1fae2c2e33f3c066927ee43bf056ec`, including the frozen benchmark.
- `actual-orchestration/`: the exact external build, metadata export, and
  control/candidate/final helpers. `.py.txt` preserves source bytes without
  importing the historical scripts as current package code.
- `paired-result.json`, `reviewed-summary.json`: actual phase results and the
  reviewed outer-bundle identity. The outer bundle was 76,372 bytes, SHA-256
  `f3a564f3df1e20129eb2f888087fc2e382b83e6d4db775540310c5d86f3404c4`.
- `later-unmeasured-pi2/`: a later page-chunk-size proposal and completion receipt,
  preserved as its original unmeasured snapshot. Its later actual measurements
  live separately in `pi2-measured/`; they do not rewrite this completion receipt.

The external helpers call canonical `configuration_delivery`, `measure`, and
`decision` functions. They do not invoke the canonical unattended harness loop.
The retained source shows the real isolation, mounted model, internal Docker
network, trace fsync, exact-owner cleanup, and fresh-final selection path. No GPU
or model API action is run by reading or validating this packet.

The Pi1 transcript metadata covers its successful continuation only. Earlier
HTTP 529 and output-length sessions remain distinct failed history. Pi1's
configured/requested 16,384 output tokens were capped to 8,192 on the historical
wire. The later Pi2 gateway's effective 16,384 cap must not be backdated to Pi1.

## Offline reproduction

From a normal Git checkout, use the repository's cached/locked development
dependencies and run:

```text
python -B -m unittest discover -s tasks/harness-design/harness/tests -t tasks/harness-design/harness -v
python -B -m tools.check_integrity --base 81aead87d78ed468c4c374fb42921471b44c3f80
```

`tests.test_current_delivery_manifest` recomputes every inventoried SHA-256/size,
checks the platform/config identities, verifies all three 30-request reports and
their six correctness gates, checks five repetitions per prompt against the
golden outputs, and verifies that the failed candidate has zero traces and no
invented report. Historical provenance assertions continue to use the preserved
26 October manifest with their original expectations.

`inventory.json` excludes itself and explanatory docs to avoid circular hashes.
Verbatim raw evidence is marked `-text` in the task's `.gitattributes`; line-ending
normalization must not change its hashes. The selected image is already publicly
available: [PR 5](https://github.com/sharonbasovich/performance_takehome/pull/5)
contains complete anonymous-graph and Docker-pull/help verification. This packet
does not download the 6 GB image or include any model weights.

Re-running GPU measurements or paid Pi proposals is a separate authorized action.
The historical external scripts contain an expired hard stop and host-specific
paths; they are reproducibility evidence, not a current deployment command.
For a future canonical unattended run use the current `harness/run.py`, the
correct `--development-benchmark` option, the identical LLMD profile for all
phases, fresh evidence paths, and the current [provider instructions](../../PI-PROVIDER.md).
Never overwrite the historical main `results.tsv` or treat software tests as a
new GPU result.

## Four-phase TSV schema

`results.tsv` uses tab-separated fields:

`phase, status, image_digest, measured_requests, gates_passed, startup_s, elapsed_s, outcome, kept`.

The baseline, control and selected-final rows each record 30 measured requests.
The candidate row records zero, `PARTIAL_FAILURE`, blank gate/timing values,
`gate_failed`, and `kept=False`. This TSV is a compact index into the raw files;
it is not the canonical loop's experiment ledger or a performance comparison.
The original main 14-row CPU ledger remains unchanged and its old FTGR/keep
decisions remain invalid performance evidence.
