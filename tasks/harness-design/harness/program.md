# Agent program: unattended LLMD optimization (Task 2)

You are the proposer inside an automated loop. Each call you get this program,
the Pi profile, the budget summary, and the history of every attempt so far.
You output exactly ONE experiment: a hypothesis plus a unified diff against the
build context. The harness builds a fresh image, measures it, and keeps it only
if it is correct and significantly better. You never run docker or servers.

## Rules (non-negotiable)

1. **One change per attempt.** A patch edits one knob (one `ARG` default, one
   CMD flag, or one build option). Two knobs in one patch cannot be attributed.
2. **Correctness first.** Any change that alters greedy outputs on the golden
   prompts, truncates output, breaks `finish_reason`, or breaks streamed-token
   vs `usage` accounting is rejected (`gate_failed`) no matter how fast it is.
3. **Same model, same tokenizer, same greedy semantics.** Speculative decoding
   (`--speculative-drafter-model`, `--speculative-draft-count`) is allowed ONLY
   if the drafter is the built-in `native` drafter or a drafter whose accepted
   tokens are verified by the target model, so greedy outputs are bit-identical.
   `--topk` must stay at a value that does not change argmax sampling at
   temperature 0. Changing the model path, quantization, tokenizer, chat
   template, or stop behaviour is out of scope: propose nothing of the kind.
4. **Real flags only.** Use the flags the pinned binary prints in `--help`
   (listed below). `--io-impl=zio` is accepted but undocumented: keep it, do
   not invent other `--io-impl` values. Unknown flags make the binary exit 1
   (`error: unexpected argument`), which the loop logs as `error`.
5. **Read the history.** Do not repeat an experiment with the same outcome. If a
   knob regressed, try the opposite direction once, then move on. Prefer the
   highest-ranked untested hypothesis.
6. **Budget awareness.** Each attempt costs one full build + startup + benchmark.
   When `usable_seconds_remaining` is below two attempt durations, propose only
   low-risk config changes (no compile-flag or image-structure changes).
7. **No shortcuts.** Never special-case benchmark prompts, cache answers, or
   change what the server returns. Never touch files outside the build context.

## How to read the measurements

* `local_ttft_speedup` = baseline median TTFT / candidate median TTFT (per
  repetition medians, >1 is better).
* `local_ftgr_speedup` = candidate / baseline Etalon fluid token generation
  rate (`benchmarks.metrics.fluid_token_generation_rate`, >1 is better).
* `local_startup_s` = seconds from `docker run` until the first complete greedy
  generation; secondary metric (a startup win alone is `no_change`, a startup
  regression blocks a keep).
* Decision: 90% bootstrap CI of the ratio of medians must exclude 1.0 AND the
  effect must exceed `min_effect` (3%) to count. Otherwise `no_change`. A kept
  image becomes the new baseline, so later speedups are relative to it.
* `error` rows (build failure, startup timeout, crash) carry the failure in
  `notes` and the report; read them before proposing a neighbouring change.

## LLMD flags verified from the pinned image (`/llmd/llmd --help`, CPU run)

```
--batch-size=<number>               default 16
--token-batch-size=<number>         default 1024
--max-context-len=<number>          default 128000
--prefill-chunk-size=<number>       default 256
--page-chunk-size=<number>          default 16
--backend=<backend>                 auto, cuda_fa2, cuda_fa3, triton, mosaic_tpu (default auto)
--gpu-memory-fraction=<fraction>    default 0.9
--cache-memory-fraction=<fraction>  default 0.95
--topk=<number>                     default 50
--speculative-drafter-model=<path>  "native" or path; off by default
--speculative-draft-count=<num>
--model-name=<string>
--listen=<addr>                     default 0.0.0.0:8000 (do not change; contract port)
--io-impl=zio                       accepted, not in --help (lock default)
```

Build context for LLMD: `tasks/harness-design/Dockerfile` (ARG defaults and
the CMD line). The ENTRYPOINT `/llmd/llmd` and `--model=/models/model` are
fixed by the image contract and must not change.

## Ranked hypotheses for LLMD (MI355X target; unexecuted in this draft)

### Startup (time to first valid generation)
- **H1 telemetry off**: with egress disabled, PostHog usage reporting may block
  or retry at startup. Blank `LLMD_USAGE_STATS_ENDPOINT`/`LLMD_POSTHOG_TOKEN`
  (already default in the candidate Dockerfile; measure vs the raw base image).
  Gate: outputs unchanged.
- **H2 `--max-context-len`** 128000 -> 32768: smaller KV-page reservation and
  faster cache allocation; gate: no benchmark prompt exceeds the new limit.
- **H3 `--cache-memory-fraction`** 0.95 -> 0.80: fewer pages to pre-fill at load.
- **H4 `--gpu-memory-fraction`** 0.9 -> 0.95: more headroom may avoid
  allocation retries (risk: OOM on a shared card -> `error`).
- **H5 io impl**: `--io-impl=zio` is the only accepted value seen; probe nothing
  else (rule 4). Weight-loading improvements must come from the organizer's
  source, which is unavailable; record as a gap.

### TTFT (prefill)
- **H6 `--prefill-chunk-size`** 256 -> 1024: fewer chunked-prefill steps for
  2k-token prompts; watch fluidity of concurrent decodes (bigger chunks stall
  decode steps).
- **H7 `--token-batch-size`** 1024 -> 2048/4096: more tokens per step; same
  trade-off as H6.
- **H8 `--batch-size`** 16 -> 32: more concurrent requests admitted; TTFT under
  load drops if the scheduler was queueing.

### Smoothness (FTGR / fluidity)
- **H9 `--page-chunk-size`** 16 -> 32/64: larger KV pages, fewer page-table
  lookups per decode step; risk of fragmentation.
- **H10 `--prefill-chunk-size`** 256 -> 128: smaller chunks interleave better with
  decode -> steadier inter-token intervals (opposite direction of H6; only one
  of them can win).
- **H11 `--backend`** auto vs explicit: on ROCm only `auto`/`triton` are
  plausible; `cuda_*`/`mosaic_tpu` will fail (`error`) - do not propose them.
- **H12 speculative decoding `--speculative-drafter-model=native`** with
  `--speculative-draft-count` 2..4: higher decode rate if acceptance is high;
  rule 3 applies - greedy outputs must be bit-identical, else `gate_failed`.

### Image slimming (secondary; only after the above)
- **H13** multi-stage copy of `/llmd` onto a smaller base: shorter pull/start
  time. Only if the binary's shared-library closure is known (`ldd`); the
  ROCm runtime makes this risky -> propose last and expect `error` first.

## Stand-in engine (CPU development evidence)

For `engine=standin` the build context is `tasks/harness-design/standin/`
(llama.cpp `llama-server`). Analogous knobs: `--threads`, `--threads-batch`,
`--batch-size`, `--ubatch-size`, `--parallel`, `--flash-attn`, `--cache-type-k/v`,
`--ctx-size`, build ARGs `GGML_NATIVE`, `GGML_LTO`, `GGML_AVX*`, `GGML_OPENMP`.
The same rules apply; the scripted queue in `experiments/standin-queue.json`
is the deterministic program used when no coding-model key is present.
