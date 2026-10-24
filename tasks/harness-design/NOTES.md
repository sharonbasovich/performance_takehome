# Task 2 — Candidate notes (harness-design)

**Read this first.** Everything measured in this submission is **CPU stand-in development
evidence** produced on an 8-vCPU x86 VM against a **candidate-built llama.cpp server**, not
the organizer's LLMD image on an MI355X. No official benchmark, grading report, GPU run,
or coding-model (Pi) call happened. Where a value can only come from the real target it is
written as `UNAVAILABLE_IN_DRAFT: <why>`, never estimated.

Starter commit: `81aead87d78ed468c4c374fb42921471b44c3f80` (the organizer's `takehome-start`
tag does not exist in this draft; the only upstream commit SHA is used instead and was **not**
tagged by me). Integrity output is in the "Integrity" section below.

## Approach in one paragraph

`harness/run.py` drives an unattended loop (`abstract_harness/loop.py`): build the baseline
image -> measure it and record golden outputs -> for each attempt: budget guard, ask the
proposer for exactly one patch, copy the **last-good build context**, apply the patch, build
a fresh image (digest recorded), start it on an internal no-egress Docker network with the
model bind-mounted read-only, wait for readiness + first valid generation, run the correctness
gates, **re-measure the last-good image in the same attempt (A/B)**, measure the candidate,
decide with a prompt-stratified bootstrap, keep (retag `last-good`, promote the context) or
revert, and append one row to `results.tsv` plus a JSON development report. State is
checkpointed to `state.json` after every step so a restart resumes; SIGTERM/SIGINT finalize
and exit 3. The `llmd` engine uses the pinned image and the exact device/mount/security flags
of `tools.baseline.start_command`; the `standin` engine is the CPU stand-in used for evidence.

## Organizer-supplied vs candidate-built vs still missing

| Piece | Organizer supplied | Candidate built (stand-in) | Still missing |
| --- | --- | --- | --- |
| Serving engine | pinned LLMD image (`baseline/lock.json`), closed source | `standin/` llama.cpp `llama-server` (commit `620d2225`, tarball sha256-pinned) + SmolLM2-135M-Instruct Q8_0 GGUF (sha256-pinned) | LLMD source, MI355X/ROCm host |
| Candidate image | `baseline/Dockerfile` (reference) | `tasks/harness-design/Dockerfile` wrapper (builds on CPU; `/llmd/llmd` entrypoint + `--io-impl=zio` preserved) | a GPU run of that image |
| Pi launcher | `agent-harness/profiles.json` pins package/version/integrity/flags; no launcher | `PiProposer` (print mode, stock tools, isolation flags, task-scoped `PI_CODING_AGENT_DIR`, key by env-var name) | coding-model API key; organizer launcher |
| Proposer used for evidence | - | `ScriptedProposer` + `experiments/standin-queue.json` | - |
| Benchmark | `benchmarks/metrics.py`, `benchmarks/streaming.py` (used unmodified) | `development-benchmark.json` workload, gates, repetitions, decision rule | private official workload |
| Runner / grader | docs only | `run.py` manifest + integrity report | official grader output, receipts, profile digests |
| Budget data | `budgets.toml`, `tools/budget.py` | pre-attempt guard (`budget.py`) | reconciled billing (API spend is 0 here) |

## Reality constraints and how they were handled

* **No MI355X / ROCm**: the `llmd` engine path is implemented and unit-tested (flags, mounts,
  entrypoint, `--network none` probe) but **never executed with a model**. `docker build
  --platform linux/amd64` of the wrapper succeeded on CPU; `docker run --rm --network none
  --entrypoint /llmd/llmd <pinned> --help` exits 0 on CPU (help text is written to stderr);
  an unknown flag fails with an unexpected-argument error; `--io-impl=zio` is accepted though
  undocumented; the pinned image has **no `/bin/sh`**, so the wrapper Dockerfile has no `RUN`.
* **No coding-model key**: Pi 1.0.0 was installed from npm with the integrity hash from
  `profiles.json` (Node 22.23.4, `pi --version` prints `1.0.0`); `PiProposer` is complete up to
  the model call and refuses to start (and makes no subprocess/network call) when the key env
  var is absent. All `results.tsv` rows come from `ScriptedProposer`.
* **No organizer Pi launcher / schema / fixtures**: candidate stand-ins above; interfaces take
  config (`--engine`, `--proposer`, benchmark JSON with `schema_version`) so real pieces drop in.

## Measurement (development benchmark)

`development-benchmark.json`: 6 greedy prompts (temperature 0, top-k 1), 5 repetitions each,
`max_tokens` per prompt, streamed `/v1/chat/completions` with `stream_options.include_usage`.
Per request: TTFT = client request start -> first content delta; FTGR = protected
`benchmarks.metrics.fluid_token_generation_rate` over the per-token arrival times from
`benchmarks.streaming`; startup = container start -> readiness -> first valid complete
generation. Gates (any failure => `gate_failed`, never kept): finish reason `stop`/`length`,
non-empty content, streamed token count within tolerance of `usage.completion_tokens`,
greedy self-consistency (two identical requests give identical text), and byte-equality with
the baseline's golden outputs for every prompt.

Decision rule (`decision.py`): per prompt, median speedup candidate vs the **same-attempt**
last-good measurement; geometric mean across prompts; 90% percentile bootstrap resampled within
each prompt group (deterministic seed). `improved` requires both TTFT and FTGR not regressed,
at least one significantly improved (CI excludes 1 and effect >= 3%) and startup not
significantly worse; `regressed` if any primary metric's CI is entirely below 1; otherwise
`no_change`. Insufficient samples => `no_change`.

Why A/B inside the attempt: the first evidence runs compared each candidate with a baseline
measured many minutes earlier; background load on the shared VM drifted between the two and
produced a spurious `improved` for a no-op change. Re-measuring last-good right before the
candidate removed that bias (cost: 2x measurement time per attempt).

## Evidence: `harness/results.tsv` (stand-in CPU rows)

| experiment | kept | outcome | TTFT x | FTGR x | startup s | build s | harness note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 1 | baseline | - | - | 0.736 | 32.82 | ttft_median_s=0.0403 ftgr_median_tok_s=8.2403 reps=5 |
| 001-threads-8 | 1 | improved | 1.4206 | 1.4465 | 0.747 | 104.49 | significant improvement: ttft_s x1.421, ftgr_tok_s x1.447 |
| 002-threads-1 | 0 | regressed | 0.2126 | 0.2567 | 0.846 | 110.96 | primary metric regressed: ttft_s x0.213, ftgr_tok_s x0.257 |
| 003-ubatch-64 | 0 | no_change | 0.9329 | 0.9295 | 0.718 | 108.84 | no primary metric moved significantly |
| 004-repeat-penalty-1.5 | 0 | gate_failed | 0.9794 | 0.6219 | 0.739 | 105.79 | golden_output_match: 6 prompts differ from the baseline golden outputs (showing  |
| 005-port-8001-misconfig | 0 | error | - | - | - | 105.94 | MeasurementError: readiness timeout after 90s: ConnectionRefusedError: [Errno 11 |
| 006-avx512-on-host-without-avx512 | 0 | error | - | - | - | 105.1 | MeasurementError: engine process exited before serving /v1/models (ConnectionRef |
| 007-native-march | 0 | interrupted | - | - | - | 16.61 | interrupted by SIGTERM (RuntimeError: build failed: build failed (rc=130): #9 10 |
| 008-lto-on | 0 | no_change | 0.9767 | 0.9861 | 0.780 | 101.94 | no primary metric moved significantly |
| 009-flash-attn-on | 0 | no_change | 0.9946 | 1.0115 | 0.727 | 104.19 | no primary metric moved significantly |
| 010-parallel-4-slots | 0 | no_change | 1.0464 | 1.0764 | 0.727 | 103.5 | no primary metric moved significantly |
| 011-no-warmup | 0 | no_change | 1.0128 | 1.0067 | 0.710 | 103.07 | no primary metric moved significantly |
| 012-kv-cache-q8 | 0 | gate_failed | 0.9547 | 0.9810 | 0.718 | 106.4 | golden_output_match: 3 prompts differ from the baseline golden outputs: ['colors |
| 013-openmp-off-cold-rebuild | 1 | improved | 1.0713 | 1.1145 | 0.714 | 101.29 | significant improvement: ftgr_tok_s x1.114 |

Speedups are candidate vs the same-attempt re-measurement of the last-good image (>1 = faster). All 14 rows were produced by **one** queue run from the committed harness tree (`source_commit` = `45fc163eba7c`, the commit whose code wrote them): one `run.py run ... --no-cache` invocation, a real SIGTERM injected while `007-native-march` was building (row `interrupted`, exit 3), and a second invocation that resumed from `state.json` and finished the queue. Every build in this set is an uncached llama.cpp compile (`build s` column, `build.no_cache: true` in each report). `012-kv-cache-q8` is rejected by the golden-output gate; `013-openmp-off-cold-rebuild` was kept (x1.07 TTFT / x1.11 FTGR, CI excludes 1). `error` rows have blank metrics (blank != 0) and GPU hours are blank because `--gpus 0`.

Every row was written by `run.py`; nothing was hand-edited.  Per-attempt JSON reports with raw
samples, container commands and log tails are in `harness/reports/`; patches in
`harness/patches/`. `error` rows come from fault injection (a wrong `--port` so readiness
never arrives; `GGML_AVX512=ON` on a host without AVX-512 so the binary dies at startup),
`gate_failed` from `--repeat-penalty 1.5` (changes greedy output -> golden mismatch), and
`interrupted` from a real SIGTERM sent while an experiment was in its `building` stage; the
next invocation resumed from `state.json` and continued the queue.

## Failures and bugs found on the way (all fixed unless noted)

1. Wrapper Dockerfile with `RUN printf` failed: pinned LLMD image has no `/bin/sh`.
2. Pooled bootstrap over heterogeneous prompts gave CIs too wide to ever decide -> stratified.
3. Queue edits that assumed a previous candidate was kept failed to apply -> regex edits.
4. `--n-predict 8` did not trip the golden gate because the client sends `max_tokens` ->
   replaced by `--repeat-penalty 1.5`.
5. Baseline drift under host load (see A/B above).
6. Candidates were built from the pristine context instead of the last-good context, so after
   the first keep every candidate silently lacked the kept change and "regressed" by the same
   ratio -> persistent `last-good-context` promoted on every keep. Runs 1-4 were discarded.
7. Publishing a host port on an `--internal` network does not work -> container IP is used.
8. Pi cost accounting over-counted: JSON mode attaches the running `usage` to every
   `message_update` delta (`dist/modes/json-event.js`), so summing every `cost.total` in the
   transcript multiplied the spend. Fixed to count only `message_end` events; found while
   building the Pi test double (below).
9. Adversarial pass (reviewer-requested) found and fixed: a corrupt/truncated `state.json`
   crashed on resume (now falls back to the `.bak` of the previous checkpoint, or refuses to
   start fresh with a clear error instead of duplicating the baseline row); a torn partial
   last line in `results.tsv` would have been glued to the next row (now cut off into
   `results.tsv.torn` and rejected by `validate-results`); two harness instances could share a
   state directory (now an `flock` on `harness.lock`, exit 4); a backwards wall-clock step
   could extend the lease (budgets now use a clamped, persisted timestamp); a model error
   inside Pi (`stopReason: error`) was indistinguishable from a crash (now surfaced with its
   `errorMessage` and the spend so far). Container-exits-before-readiness and ready-but-every-
   request-500s paths were already errors; the latter now has a test against a stub server.
10. First regenerated evidence set (discarded) showed the last-good A/B arm 2-3x slower in some
    attempts than in others (threads-8 FTGR median 13.9 vs 4.4 vs 7.4): BuildKit's post-build
    export/GC after each `--no-cache` compile was still running when the first measurement arm
    started. Fixed by `procs.wait_for_quiet_host()` (bounded wait for >= 85% idle over 3 samples,
    recorded as `host_quiet_before_start` in every container record); the committed set shows
    consistent last-good medians (12.7-13.7 tok/s) across attempts.

## Pi test double (what `PiProposer` was actually tested against)

No model was ever called. `harness/tests/fixtures/fake_pi.py` is a CANDIDATE-BUILT executable
that speaks the pinned CLI's non-interactive protocol, derived by reading the installed
`@earendil-works/pi-coding-agent@1.0.0` package:

| Behaviour | Source in the installed package |
| --- | --- |
| `--print` / `-p` flag, `@file` prompt arguments, `--mode` text/json/rpc | `dist/cli/args.js` L134-135, L224-225, L47 |
| First stdout line is the `SessionHeader` `{type:"session", version, id, timestamp, cwd}` | `dist/modes/print-mode.js` L97-101; `dist/core/session-manager.d.ts` L5-12 |
| One JSON line per session event | `dist/modes/print-mode.js` L85-87 (`JSON.stringify(toJsonEvent(event))`) |
| `message_update` rewritten to `{type, usage, assistantMessageEvent}` | `dist/modes/json-event.js` (`toJsonEvent`) |
| Event types `agent_start`, `turn_start`, `message_start`, `message_update`, `message_end`, `tool_execution_start/update/end`, `turn_end`, `agent_end` | `node_modules/@earendil-works/pi-agent-core/dist/types.d.ts` L451-483 |
| `usage` = `{input, output, cacheRead, cacheWrite, totalTokens, cost:{input, output, cacheRead, cacheWrite, total}}` | `node_modules/@earendil-works/pi-ai/dist/types.d.ts` L292-310 |
| Assistant `stopReason` (`stop`/`length`/`toolUse`/`error`/`aborted`) and `errorMessage` | `node_modules/@earendil-works/pi-ai/dist/types.d.ts` L386-388 |

`FakePiEndToEndTest` drives the real `PiProposer` against it: a successful run yields exactly one
`patch -p1`-applicable diff and the spend from `message_end` events only (0.0048 + 0.0075);
non-JSON lines in the stream are skipped without losing cost; a model error (`402
insufficient_quota`) is surfaced with its message and spend; a non-zero exit, a hang (killed
at the timeout) and a run that edits nothing are all `ProposerError`s. Not verified: that a
real provider's error text and exit code match the fixture's; the fixture's values are
illustrative, its *shapes* are the ones in the type definitions above.

## Round-3 review fixes (independent cold review of 62ab024)

Every finding below was reproduced, fixed and covered by a test in `harness/tests/`
(`test_hardening.py`, `test_docs.py`, `test_provenance.py`, `CrashBetweenWritesTest`):

| Finding | Fix | Test |
| --- | --- | --- |
| Scripted edit with an absolute `file` path wrote to a host file | `proposers.contained_path()` (relative, no `..`, resolves inside the context, no symlink components); contexts with escaping symlinks are refused before copying; `apply_patch` rejects symlinks it created that leave the context; copies preserve symlinks instead of following them | `PathContainmentTest` (absolute, `..` variants, symlink file, symlinked dir, case variant, patch-created symlink) |
| Startup regression guard was dead code (1 sample vs `min_samples=3`) | `decision.startup_hard_gate()`: single-sample hard gate at 1.5x (`--startup-regression-limit`), evaluated before the primary metrics; docs now say exactly this | `StartupHardGateTest` (100x slower startup + TTFT win -> `regressed`) |
| `kill -9` between row append and state save duplicated the row and overwrote the report | `InProgress` carries `attempt_index`/`report_path`/`row_written`; `_append_row` is idempotent on experiment id; recovery clears the marker without a row when the row exists, never overwrites an existing report (`.recovered.json`), and `_reconcile_attempt_index()` never reuses a number already in `results.tsv` (also covers a `.bak` rewind); `validate-results` rejects duplicate ids | `CrashBetweenWritesTest` (report-only, row-without-save, `.bak` rewind, duplicate id) |
| Documented `fetch-standin-model --model-dir` did not run | README fixed (`--dest`); organizer example rewritten to the real CLI | `test_docs.py` parses every documented `run.py` line with the real parser |
| `source_commit` named a commit without the code | `_git_describe()` records HEAD and refuses to run on a dirty `tasks/harness-design` (code paths only; evidence outputs are ignored) unless `--allow-dirty` (then `-dirty` suffix); `harness_tree_sha256` of the code + inputs stored in state and manifest; **all evidence rows were regenerated from the committed tree** | `ProvenanceTest` |
| Budget guard could not bound an attempt | estimate = max(configured, p90 of observed attempt durations); proposer USD estimate passed; every stage timeout is clamped to a per-attempt deadline = min(worst case from timeouts, usable lease window) | `BudgetBoundTest` |
| `results.validate()` gaps | rejects `improved` rows without a speedup > 1 (none below 0.95), NaN/inf/non-numeric numbers (named error), non-hex digests, malformed timestamps; file-level: duplicate ids, duplicate rows, non-monotonic timestamps | `ResultsValidationTest` |
| `load_benchmark()` gaps | `BenchmarkError` for non-positive/non-int repetitions and token counts, non-positive timeouts, prompts without `id`/`prompt`, bad `startup_probe` | `BenchmarkValidationTest` |
| Complete last row without newline was dropped to `.torn` | fragment is parsed first; a valid row is kept (newline added, logged) | `test_complete_last_row_without_newline_is_kept` |
| Lock taken after header write/state read; results path unlocked | both `harness.lock` and `<results>.lock` are taken in `Harness.__init__` before any read/write | `EarlyLockTest` |
| `KeyError`/`TypeError` escaped `run()` without `finalize()` | queue entries are schema-checked up front (`ScriptedProposer.validate_queue`); `run()` catches `Exception`, logs the traceback, finalizes, exits 2 | `test_queue_schema_errors_are_named` |
| Signal handler raised inside the handler and `SIG_IGN`ed a second signal | first signal sets a flag (child processes are aborted via `should_abort`, the loop stops at the next checkpoint and finalizes); a second signal aborts even `finalize()`; a third is the default action | `SigtermSubprocessTest` |
| Hard-coded manifest literals; empty `agent_transcripts` | repository URL from `git remote`, Pi pins from `agent-harness/profiles.json`, llama.cpp commit from the stand-in Dockerfile; transcripts collected from reports | reconciled by `validate-results` + manifest tests |
| FTGR silently dropped <= 1-token samples; `gpu_hours_cumulative=0.0000` with no GPU | dropped count reported in measurement notes; GPU hours blank when `--gpus 0` | `test_measure.py`, evidence rows |
| Tautological commit check in `standin/Dockerfile` | `ARG LLAMA_CPP_COMMIT` is now part of the `ADD --checksum` URL, so commit and checksum must change together | build of the evidence images |

**What the "digest" is.** With `docker buildx build --load` the only locally resolvable identity
is the image *config ID* (`docker image inspect --format {{.Id}}`); that is what `image_digest`
holds and why it equals `image_id` in every report. A registry manifest digest exists only after
a push (`manifest.json` says which kind it recorded).

**Pi sandboxing (known limitation).** The organizer contract requires plain Pi 1.0.0 with the
stock `bash` tool, so `PiProposer` runs it as a host process. Mitigations in place: cwd is the
scratch copy of the build context, the environment is scrubbed to PATH/HOME/LANG plus the named
key, `PI_CODING_AGENT_DIR` points at a task-scoped directory, the resulting tree is diffed and the
patch is containment-checked before use. Not in place: a container or `bwrap` jail; on a shared
host that is a real risk and is called out in the PR. `--no-approve` in 1.0.0 means "ignore
project-local files" (`dist/cli/args.js` L219, `projectTrustOverride`), not approval skipping.

## Limitations (honest)

* Stand-in results say nothing about LLMD on MI355X; they prove the loop, not the hypotheses.
* 8 shared vCPUs: absolute numbers are noisy; only the paired A/B ratios are meaningful.
* Scripted proposer only for the evidence rows; the Pi path is exercised end to end against the
  test double above but never against a real model/provider.
* `extra_request_fields.cache_prompt=false` in the benchmark is llama.cpp-specific; set it to
  `{}` for LLMD if it rejects unknown fields (documented in the JSON).
* GPU-hours are allocation x elapsed; API spend is only known when the proposer reports cost.
* One `interrupted` experiment (`007`) was not retried; the queue continued past it by design.

## Runbook when an MI355X host and a coding-model key exist

```sh
git clone <fork> && cd performance_takehome && git checkout submission/harness-design
uv sync --frozen --extra dev
docker pull --platform linux/amd64 docker.io/zmlai/llmd@sha256:0a2cd01a2e53c78934a8cfef66f8668da7666be4954a5d18b72df089c54ea34f
# 1. contract probe (no GPU needed)
docker build --platform linux/amd64 -t llmd-candidate:probe tasks/harness-design
docker run --rm --network none --entrypoint /llmd/llmd llmd-candidate:probe --help
# 2. Pi distribution (exact pin from agent-harness/profiles.json)
mkdir -p /opt/pi && cd /opt/pi && npm init -y >/dev/null && npm install @earendil-works/pi-coding-agent@1.0.0 && ./node_modules/.bin/pi --version && cd -
# 3. run (the key is read from the named env var only)
export HARNESS_LLM_API_KEY=...
uv run --frozen python tasks/harness-design/harness/run.py run --engine llmd \
  --model-dir /path/to/model-repo --render-device /dev/dri/renderD128 \
  --proposer pi --pi-bin /opt/pi/node_modules/.bin/pi --api-key-env HARNESS_LLM_API_KEY \
  --experiments tasks/harness-design/harness/experiments/standin-queue.json \
  --state-dir /var/tmp/harness-state --out tasks/harness-design/submission.json \
  --results tasks/harness-design/harness/results.tsv \
  --budget-minutes 1380 --api-spend-limit-usd 40 --gpus 1 --gpu-hours 24
# 4. verify
uv run --frozen python tasks/harness-design/harness/run.py validate-results --results tasks/harness-design/harness/results.tsv
python -B -m tools.check_integrity --base 81aead87d78ed468c4c374fb42921471b44c3f80
```
First experiments to run on the real target are ranked in `harness/program.md` (startup:
`--cache-memory-fraction`, telemetry-with-no-egress check; TTFT: `--prefill-chunk-size`,
`--token-batch-size`; smoothness: `--page-chunk-size`, `--batch-size`; speculative decoding
only with the same model/tokenizer and greedy-equal outputs).

## Integrity

```
$ python -B -m tools.check_integrity --base 81aead87d78ed468c4c374fb42921471b44c3f80
PASS: protected organizer files unchanged from 81aead87d78ed468c4c374fb42921471b44c3f80
```
The organizer `takehome-start` tag is absent in this draft fork, so the single upstream commit SHA is passed with `--base`; no tag was created.

## Effort and resource use

Active agent time: one unattended session (~a working day equivalent). API charges: 0 (no
coding-model calls). GPU-hours: 0 (none allocated). CPU: 8 vCPU VM; the committed evidence run
(14 rows, one queue, SIGTERM + resume) spanned 2026-10-24T09:42:50Z..10:08:59Z (26 min 9 s). Every build
was an uncached llama.cpp compile (`--no-cache`): 101-111 s per attempt image, 32.8 s for the baseline
image, 16.6 s into the `007` build when SIGTERM arrived. Per attempt ~2.5 min including the quiet-host
wait (3 s each arm), A/B re-measure and candidate measurement; 95 s extra for the readiness-timeout fault. Cut: Pi end-to-end run (no key),
LLMD execution (no GPU), more repetitions (time).
