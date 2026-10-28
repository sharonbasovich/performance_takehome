# Agent program: one genuine optimization proposal (Task 2)

Choose your own hypothesis and write exactly ONE attributable patch. The controller
supplies the current Dockerfile, selected development benchmark, baseline image/model
catalog, runtime binding, stock Pi profile, budget and attempt history below. Use those
actual inputs, including any changed last-good Dockerfile. No optimization patch or
winning knob has been selected for you. Build, inference, measurement and keep/revert
belong to the harness; you never run Docker or servers.

## Scope and contract

For `engine=llmd`, the scratch build context is the repository root. Edit **only
`tasks/harness-design/Dockerfile`**, one knob per attempt (one flag or one ENV variable).
Preserve the current file's other bytes. The pinned image has no shell; no `RUN` steps.
Keep `/llmd/llmd`, `--model=/models/model`, port 8000, `--io-impl=zio` and
`--max-context-len=128000`. Do not lower the context contract because short prompts fit.
Do not change the model, weights, tokenizer, quantization, chat template, greedy
sampling, stop behavior, request profile, benchmark, measurement, gates or accounting.
Never special-case prompts or cache answers. Read no private evidence or credentials.
Do not install tools, make network calls or run inference yourself.

The renderer's baseline catalog identifies available pinned models; the runtime
binding names the mounted model directory and arguments. Do not infer which snapshot
was mounted from a catalog entry alone. Full file pins are separately preflighted and
retained by the runner. If essential context is missing, state that and stop.

The setup is already supplied. If a file check is necessary, batch only the actual
scratch Dockerfile and necessary pinned input checks in one read-only tool action.
Do not repeat a repository investigation. Read the history, choose your mechanism,
write your own patch and metadata, then stop. A concise prompt does not promise that
provider latency, response limits or billing have been repaired.

## Frozen LLMD workload

The controller must explicitly select
`tasks/harness-design/harness/development-benchmark.llmd.json`; the CLI default is a
different generic benchmark. Read the **selected** benchmark supplied below. Its
`llmd_closed_thinking_v1` profile fixes temperature 0, `top_k=1`, empty-thinking
assistant prefill `</think>\n\n`, `continue_final_message=true`, and
`add_generation_prompt=false`, identically for startup and measurement. This serving
profile and the stock Pi tool profile are separate contracts, neither a speed change.

The LLMD development workload is sequential, six short prompts × five repetitions.
Output ceilings are colors 48, capital 48, sum 16, haiku 64, explain 96 and list 48
(the top-level default 48 does not override individual ceilings). The startup probe
is “Say hello.” with four tokens. Each request has a 120-second timeout. Historical
baseline inputs were 15–27 tokens. This does not measure concurrent queueing or long
prefill; do not claim those benefits or change the benchmark to make a knob look good.

## Decision you are optimizing against

`decision.py::bootstrap_speedup` groups samples by prompt. Each prompt's ratio uses
the median over its repetitions: baseline/candidate for TTFT, candidate/baseline for
Etalon FTGR. The reported speedup is the geometric mean of those prompt ratios
(>1 is better). The seeded 2,000-resample percentile bootstrap resamples within prompt
groups and computes a 90% CI. A gain needs the lower bound above 1 and at least the
configured 3% point effect; a significant primary-metric regression vetoes a keep.
This is not a ratio of pooled per-repetition medians.

All correctness gates must pass: golden greedy outputs, accepted finish reasons,
complete output and streamed-token/usage accounting. One cold startup is measured per
side: more than 1.5× last-good startup is a hard regression gate. Startup improvement
alone is `no_change`. A kept candidate becomes the baseline for the next attempt.
Read error/regression history before selecting a neighboring change.

## Unmeasured mechanisms to consider

Choose against this workload and history, one knob only. These are hypotheses, not
performance evidence or instructions to copy a prepared patch.

* KV page size (`--page-chunk-size`) may change decode page-table overhead, with
  fragmentation/startup risk. A native drafter (`--speculative-drafter-model=native`)
  may help only when target verification preserves bit-identical greedy output.
  Adding a drafter and changing `--speculative-draft-count` are two separate attempts.
* Cache/GPU memory fractions may affect allocation overhead; changing either risks
  startup failure or OOM. No benefit has been measured here.
* Larger prefill/token batches or more admitted requests have no demonstrated
  long-prefill/concurrency benefit on these short sequential prompts. CPU-supported
  syntax does not establish ROCm/model support or a GPU gain.
* Both telemetry ENV declarations are commented out in the original wrapper.
  Changing **one** declaration is one variable; uncommenting both is two variables.
  Their startup benefit is unmeasured and cannot alone earn a keep.

Use only documented pinned binary flags. Current values are in the supplied
Dockerfile. Verified help names include `--batch-size`, `--token-batch-size`,
`--max-context-len`, `--prefill-chunk-size`, `--page-chunk-size`, `--backend`,
`--gpu-memory-fraction`, `--cache-memory-fraction`, `--topk`,
`--speculative-drafter-model`, `--speculative-draft-count`, `--model-name`, and
`--listen`. `--io-impl=zio` is accepted but absent from help; invent no other value.
Keep backend `auto` unless your own supported alternative has a defensible mechanism;
do not add CUDA/TPU options. Help availability is not performance evidence.

The real baseline was measured at `09f52c25af380a0daefdea3a183fe45a6ec75730`.
The genuine Pi attempt failed at a 120-second upstream cap before producing a patch;
no Pi optimization cycle or measured gain exists. Older CPU stand-in keeps were
invalidated by an interval-adapter bug and are not LLMD improvement evidence. The
missing historical fresh-revalidation report/traces and provider body cannot be
recreated by new results.

## CPU stand-in

For `engine=standin`, use only its supplied Dockerfile and scratch build context.
Analogous knobs include threads, batch sizes and build ARGs. Preserve the same
correctness and attribution rules. Scripted/fake-provider CPU fixtures test harness
behavior; they are not genuine Pi work or target hardware performance evidence.

Write the renderer-specified unified diff relative to the scratch context (for LLMD,
`a/tasks/harness-design/Dockerfile` and `b/tasks/harness-design/Dockerfile`) and metadata
with `experiment`, `hypothesis`, `notes`. Identify intended metric, physical mechanism
and correctness risk; never assert an unmeasured gain. Then stop.
