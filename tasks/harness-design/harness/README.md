# Task 2 — Candidate optimization harness contract (draft)

You start from the [plain Pi 1.0 profile](../../../agent-harness/README.md), implement
its optimization loop, and choose development measurements. No enhanced Task 1 harness
or prebuilt optimizer is supplied. The main output is an image digest, not a benchmark score. The organizer's official benchmark is private and
runs offline after submission; it is not an input to your harness. `run.py` is intentionally
not a solved optimizer in this starter repository. All paths below are repository-root-relative.

Example candidate-defined invocation:

```text
python tasks/harness-design/harness/run.py run \
  --engine llmd --model-dir /path/to/model-repo \
  --baseline baseline/lock.json \
  --development-benchmark tasks/harness-design/harness/development-benchmark.json \
  --budget-minutes 360 \
  --api-spend-limit-usd 200 \
  --state-dir /var/tmp/harness-state \
  --out tasks/harness-design/submission.json \
  --results tasks/harness-design/harness/results.tsv \
  --reports-dir tasks/harness-design/harness/reports \
  --patches-dir tasks/harness-design/harness/patches \
  --overwrite-evidence
```

(`--out`/`--results`/`--reports-dir`/`--patches-dir` default to files under `--state-dir`;
pointing any of them at git-tracked files is refused with exit 2 unless `--overwrite-evidence`
is given, so a casual run can never overwrite the committed evidence.)

You define the local measurement configuration/schema and implement its invocation.
No organizer benchmark manifest, grader binary, or score endpoint is supplied.
Runtime invocation is a subset of the Task 2 candidate allowance, not an extra grant.
Task 1 credentials/leases cannot extend it.

The organizer supplies credential/balance/lease interfaces before task release. A CLI
flag is not a hard API spend cap. The actual proxy and compute leases enforce limits.

## Required behavior

1. Start from the pinned plain Pi 1.0.0 distribution with isolated task configuration.
   Preserve the supplied baseline; put candidate orchestration/prompts/tools under this
   directory or a declared Pi-derived fork/overlay. Record base identity, enhancements,
   effective tool/resources, transcripts, and coding-model usage. Read model/runtime/budget
   inputs; consult `program.md`, source, profiles, server logs, and raw local measurements. Do not embed benchmark answers or request-specific shortcuts.
2. Establish a measured development baseline, including correctness/completeness checks.
   Keep its image as a recoverable last-good state.
3. Form a hypothesis, save the patch/config, build a fresh candidate image, and resolve
   its digest. Isolate one engine experiment at a time on the assigned GPU.
4. Measure using your own development workloads and checks. Explain the keep/reject
   policy, noise handling, and limitations. Profiles or smoke success alone cannot
   substantiate a performance claim. Local checks do not certify an official grade.
5. Log every attempt, including build errors, startup timeouts, correctness failures,
   reversions, and interrupted runs. Keep the image/log/patch/config artifacts needed for replay.
6. Recover without a human. Terminate child process groups/containers, clean temporary
   state, restore last-good image/config, and continue if time and credits remain.
   Never `git reset --hard` an arbitrary user worktree.
7. Check API balance, lease time, and remaining compute before each experiment. Reserve
   final build/validation/submission time. On exhaustion or SIGTERM return the last image
   that passed your development checks; do not start a run that cannot fit the remaining lease.
8. Write the task-scoped `--out` manifest with `task=harness-design`, final image digest,
   development measurement configuration/evidence, and provenance on exit. Keep source/build
   and manifest synchronized; a launch tag cannot masquerade as a digest.
9. Run the [protected-file integrity check](../../../docs/INTEGRITY.md) against the
   released starter and record the result. Candidate harness diffs are expected; changes
   to supplied infrastructure/tests are not.

No requirement to discover a magic improvement. A reliable bounded loop with honest
negative results is better than fabricated progress or an optimizer that needs rescue.

## Experiment log

`results.tsv` contains one row per attempt. `image_digest` may be empty if the build
failed. `api_usd_cumulative` is reconciled with organizer billing, not model-estimated
spend. `gpu_hours_cumulative` comes from allocation accounting, not utilization.
Missing metrics stay blank, never zero. TSV fields escape tabs/newlines; artifacts keep
full multiline descriptions. Store raw local reports outside this summary table.

Outcome values: `baseline`, `improved`, `no_change`, `regressed`, `gate_failed`, `error`,
`interrupted`. These describe **your development checks only**. `kept` is `1` or `0`;
a kept state must have an image and a passing local validation report.

The `local_ttft_speedup`, `local_ftgr_speedup`, and `local_startup_s` columns are optional
local summaries, not official metrics. If you use them, document their definitions and
workloads in the referenced `development_report`; add clearly named columns for other
local metrics. Retain distributions, repetitions, failures, uncertainty, and measurement
cost in raw reports. There are no official grader reports to attach during development.

---

# Candidate implementation (CANDIDATE-BUILT; everything below this line is the candidate's)

The contract above is the organizer's draft and is kept verbatim. The implementation lives
next to it:

| Path | What it is |
| --- | --- |
| `run.py` | CLI: `run`, `validate-results`, `fetch-standin-model`, `retag-last-good` |
| `abstract_harness/engines.py` | `Engine` abstraction: `LlmdEngine` (pinned `baseline/lock.json` image, same device/mount/security flags as `tools.baseline.start_command`, internal no-egress network instead of `--publish`) and `StandinEngine` (candidate-built llama.cpp CPU server, `../standin/`) |
| `abstract_harness/proposers.py` | `PiProposer` (pinned Pi 1.0.0, print mode, stock tools, isolation flags, key by env-var name only) and `ScriptedProposer` (deterministic queue; used for all evidence here because no coding-model key was available) |
| `abstract_harness/measure.py` | development benchmark runner: TTFT, Etalon FTGR via protected `benchmarks.metrics`, startup-to-first-valid-generation, correctness gates |
| `abstract_harness/decision.py` | prompt-stratified bootstrap decision rule (`improved` / `regressed` / `no_change` / `gate_failed`) |
| `abstract_harness/loop.py` | the unattended loop: build -> start -> gate -> A/B measure -> decide -> keep/revert; checkpoints, SIGTERM/SIGINT handling, resume from `state.json` |
| `abstract_harness/budget.py` | pre-attempt guard: API USD, GPU-hours (= allocated x elapsed), lease deadline, reserved final window |
| `abstract_harness/docker_runtime.py`, `procs.py` | Docker/BuildKit wrappers, process-group aware timeouts |
| `abstract_harness/results.py`, `state.py`, `manifest.py` | exact `results.tsv` schema + vocabulary, atomic on-disk state, final `--out` manifest + integrity report |
| `development-benchmark.json` | the candidate development workload (prompts, repetitions, gates, thresholds) |
| `experiments/standin-queue.json` | the deterministic experiment queue used to produce `results.tsv` (includes the fault-injection entries) |
| `patches/`, `reports/` | per-attempt unified diffs and development reports written by the loop |
| `tests/` | task-local unittest suite |

## Run it

Stand-in engine on CPU (what produced the committed `results.tsv`; needs Docker + ~2 GB disk,
network only for the one-time model download and the first image build):

```sh
uv run --frozen python tasks/harness-design/harness/run.py fetch-standin-model --dest /tmp/standin-model
uv run --frozen python tasks/harness-design/harness/run.py run \
  --engine standin --model-dir /tmp/standin-model \
  --experiments tasks/harness-design/harness/experiments/standin-queue.json \
  --state-dir /tmp/harness-state --out /tmp/harness-state/submission.json \
  --budget-minutes 120 --api-spend-limit-usd 0 --gpus 0 --standin-cpus 8
```

Everything this writes (`results.tsv`, `reports/`, `patches/`, `submission.json`, `state.json`)
lands under `/tmp/harness-state`; the checkout stays clean (`git status --short` is empty
afterwards). To *replace* the committed evidence instead, add `--results
tasks/harness-design/harness/results.tsv --reports-dir tasks/harness-design/harness/reports
--patches-dir tasks/harness-design/harness/patches --out tasks/harness-design/submission.json
--overwrite-evidence` (and `--no-cache` for real builds). `--manifest-only` rewrites
`submission.json` + `reports/build-provenance.json` + `reports/agent-provenance.json` from an
existing state directory without running attempts, keeping the state's `source_commit` and
`harness_tree_sha256` (that is how the committed manifest was regenerated after the Round-4
metadata fixes; the rows were not touched).

Real target (MI355X host + coding-model key; **not executed in this draft**):

```sh
export ANTHROPIC_API_KEY=...             # never passed on the command line, never logged
uv run --frozen python tasks/harness-design/harness/run.py run \
  --engine llmd --model-dir /path/to/model-repo \
  --proposer pi --pi-bin /opt/pi/node_modules/.bin/pi \
  --pi-provider anthropic --api-key-env ANTHROPIC_API_KEY \
  --state-dir /var/tmp/harness-state --out /var/tmp/harness-state/submission.json \
  --budget-minutes 1380 --api-spend-limit-usd 40 --gpus 1 --gpu-hours 24
```

The key variable must have the provider's native name: `ANTHROPIC_API_KEY` for Anthropic,
or `OPENAI_API_KEY` with `--pi-provider openai`. `--api-key-env` selects the variable to
forward; it does not rename an arbitrary alias into a provider credential.

Send `SIGTERM` at any time: the loop finishes the current step boundary, logs the attempt
as `interrupted`, keeps the last-good image, writes the manifest and exits 3. Re-running the
same command resumes from `state.json`.

## Tests (one command, offline, no GPU; Docker-only tests skip when the image is absent)

```sh
uv run --frozen python -m unittest discover -s tasks/harness-design/harness/tests -t tasks/harness-design/harness -v
```

## Validate the log

```sh
uv run --frozen python tasks/harness-design/harness/run.py validate-results --results tasks/harness-design/harness/results.tsv
```

Add `--no-cache` to a `run` invocation to force every image build in that invocation to be a
full uncached rebuild (recorded as `build.no_cache` in the attempt report); the harness exits 4
if another instance already holds `<state-dir>/harness.lock` or if `state.json` is corrupt
and no `.bak` checkpoint exists.
