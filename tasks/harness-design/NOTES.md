# Task 2 — Actual Pi proposal, rejected candidate, selected baseline

The selected image is the already published LLMD baseline:

`ghcr.io/sharonbasovich/performance_takehome-task2-llmd@sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d`

On 28 October, a genuine stock Pi 1.0.0 proposal changed one Docker CMD knob to
`--speculative-drafter-model=native`. The candidate passed the canonical
`llmd-config-v1` source guard and built successfully, preserving the baseline's
23 layers and entrypoint. It then failed at startup while resolving the DFlash
model repository (`FileNotFound`), before any measured request. It was rejected.
The baseline was selected again and a **fresh final 30-request run passed all
six development correctness gates**. No optimized image or speedup is claimed.

| Actual phase | Measured requests | Result |
|---|---:|---|
| Initial baseline | 30 | All six gates passed; establishes the six golden outputs |
| Same-attempt control | 30 | All six gates passed against those golden outputs |
| Native-drafter candidate | 0 | Startup failure; no performance report or metric invented |
| Fresh selected final | 30 | All six gates passed on the selected baseline |

Every successful phase retains its full report and 31 durable request records,
including the startup probe. The candidate retains its empty trace file, error
receipt, and container logs. The complete small evidence, exact candidate config
and manifest, build logs, actual orchestration sources, frozen benchmark, and
reproduction instructions are in [the 28 October packet](harness/reports/live-mi355x-20261028/README.md).
The [current manifest](submission.json) binds these files and the selected image.
The development workload is six greedy prompts, five repetitions each, using
`llmd_closed_thinking_v1`; it is not the organizer's private benchmark or grade.

## What actually ran

This evidence is a genuine Pi proposal followed by the canonical source guard,
measurement functions, decision function, and a fresh selected-image final
measurement, **through external stage orchestration**. The actual helper source
is retained verbatim. It is not an execution of the canonical unattended
`Harness.run()` loop. That loop has separate software tests; software tests do
not change the attribution of this real run.

The successful Pi continuation is distinct from an earlier HTTP 529 session and
a retry that ended at the output-length limit. Its metadata-only transcript has
ten tool starts and ten tool ends, final stop reason `stop`, and artifact hashes.
No assistant reasoning, tool output, argument content, environment values, or
private provider journal is published. The cached stock Pi distribution was
verified across 1,243 files with Node 22.19.0. The continuation requested a 16,384
output-token configuration, but its historical gateway wire cap was **8,192**.
The later provider source/documentation fixes (`4960306`, `419a0bd`) reject
truncated proposals before artifact recovery and correct the flag/wire-cap
history; they do not retroactively change that session.

## Delivery and later work

The selected platform manifest above and config
`sha256:0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f`
are the baseline already published through [delivery PR 5](https://github.com/sharonbasovich/performance_takehome/pull/5).
The complete anonymous graph check verified 25 objects / 5,923,167,710 bytes;
anonymous Docker pull, image inspection, and isolated CPU help execution also
passed. These establish baseline delivery, not candidate performance. No image
layers or model weights are included in this small evidence packet, and the
rejected candidate is not tagged or described as the winner.

A later Pi proposal completed at `2026-10-28T19:38:16.133592Z`, changing only
`--page-chunk-size=16` to `64`. It is retained under `later-unmeasured-pi2/` as an
**unmeasured proposal**, with no build, GPU measurement, selected-image status,
or gain attributed to it in this packet. Its later gateway supports an effective
16,384 output-token cap; that does not change the earlier continuation's cap.
Any future experiment needs its own receipts and must preserve this rejected
candidate and baseline result.

Reported newly settled model API cost through that later proposal is
**$0.3664702**. Earlier unresolved holds remain fully reserved; errors and missing
usage are not assumed free. This figure is not a private billing reconciliation.
No financial ledger, account information, card data, provider key, or SSH material
is published. See [PI-PROVIDER.md](harness/PI-PROVIDER.md) for the corrected provider
setup and [DELIVERY-POLICY.md](harness/DELIVERY-POLICY.md) for source-only eligibility.

## Preserved history and limits

The former live manifest is preserved byte-for-byte as
[submission.live-mi355x-20261026.json](submission.live-mi355x-20261026.json),
including its original local CRLF bytes. The exact prior Git blob is also retained
as [submission.live-mi355x-20261026.git.json](submission.live-mi355x-20261026.git.json).
The former notes are [archived separately](NOTES.history-through-20261026.md).
Their statements describe that earlier state, including the failed GLM/Pi
provider attempt and the missing full 26 October revalidation records; the new
28 October reports do not reconstruct those missing records.

The main `harness/results.tsv` still has its original 14 CPU stand-in rows.
Their historical FTGR calculation and keep decisions remain invalid performance
evidence. No historical rows, raw reports, or failed-provider history were
rewritten. The new [four-phase TSV](harness/reports/live-mi355x-20261028/results.tsv)
has a separately declared schema and no candidate metric for the startup failure.
The old bot-authored [PR 3](https://github.com/sharonbasovich/performance_takehome/pull/3)
remains review history. No official organizer run or score is available.
