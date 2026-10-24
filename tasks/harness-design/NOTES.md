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

| experiment | kept | outcome | TTFT x | FTGR x | startup s | harness note |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 1 | baseline | - | - | 0.736 | ttft_median_s=0.0402 ftgr_median_tok_s=11.1355 reps=5 |
| 001-threads-8 | 1 | improved | 1.3494 | 1.4385 | 0.701 | significant improvement: ttft_s x1.349, ftgr_tok_s x1.439 |
| 002-threads-1 | 0 | regressed | 0.1925 | 0.2308 | 0.833 | primary metric regressed: ttft_s x0.193, ftgr_tok_s x0.231 |
| 003-ubatch-64 | 0 | no_change | 0.9713 | 1.0258 | 0.719 | no primary metric moved significantly |
| 004-repeat-penalty-1.5 | 0 | gate_failed | 0.9566 | 0.6836 | 0.697 | golden_output_match: 6 prompts differ from the baseline golden outputs: ['capital', 'color |
| 005-port-8001-misconfig | 0 | error | - | - | - | MeasurementError: readiness timeout after 90s: ConnectionRefusedError: [Errno 111] Connect |
| 006-avx512-on-host-without-avx512 | 0 | error | - | - | - | MeasurementError: engine process exited before serving /v1/models (ConnectionRefusedError: |
| 007-native-march | 0 | interrupted | - | - | - | interrupted by SIGTERM during stage building |
| 008-lto-on | 0 | no_change | 1.0653 | 1.0219 | 0.701 | no primary metric moved significantly |
| 009-flash-attn-on | 0 | no_change | 1.0036 | 0.9658 | 0.715 | no primary metric moved significantly |
| 010-parallel-4-slots | 0 | no_change | 0.9800 | 0.9735 | 0.706 | no primary metric moved significantly |
| 011-no-warmup | 0 | no_change | 0.7278 | 0.8212 | 0.762 | no primary metric moved significantly |
| 012-kv-cache-q8 | 0 | gate_failed | 1.2100 | 1.4361 | 0.736 | golden_output_match: 3 prompts differ from the baseline golden outputs: ['colors', 'explai |

Speedups are candidate vs the same-attempt re-measurement of the last-good image (>1 = faster). `012-kv-cache-q8` was ~1.2-1.4x faster yet rejected: quantised KV cache changed 3 of 6 greedy outputs, which is exactly the never-keep-on-correctness-failure rule. `011-no-warmup` looked ~25% slower but the bootstrap interval still covered 1.0, so it is `no_change`, not `regressed`. Rows ending with `error` have blank metrics (blank != 0).

Every row was written by `run.py`; nothing was hand-edited. Per-attempt JSON reports with raw
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

## Limitations (honest)

* Stand-in results say nothing about LLMD on MI355X; they prove the loop, not the hypotheses.
* 8 shared vCPUs: absolute numbers are noisy; only the paired A/B ratios are meaningful.
* Scripted proposer only; the Pi path stops at the key check. Pi's exact JSON event format for
  cost extraction is parsed defensively (`_cost_from_events`) but unverified against a real run.
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
(13 rows) spanned 2026-10-24T08:29:42Z..08:33:29Z (3 min 47 s). Builds in that run were Docker
layer-cache hits (0.16-0.31 s each, see `build.duration_s` in the reports) because the same
Dockerfile/flags had been compiled in four earlier, discarded development runs; a cold llama.cpp
compile on this VM takes minutes. Per attempt: ~10-18 s for build + readiness + gates + A/B
measurement, 95 s for the readiness-timeout fault. Cut: Pi end-to-end run (no key),
LLMD execution (no GPU), more repetitions (time).
