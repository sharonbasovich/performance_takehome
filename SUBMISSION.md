# Abstract take-home review handoff

This branch brings together the reviewed versions of all four tasks. Start with the
task guides below. Each task also has its own review PR and frozen source commit.
The supplied starter, shared infrastructure and baseline remain unchanged.

| Task | Start here | Review PR | Frozen task snapshot |
| --- | --- | --- | --- |
| 1 — Benchmark design | [Design](tasks/benchmark-design/DESIGN.md), [execution guide](tasks/benchmark-design/EXECUTION.md), [manifest](tasks/benchmark-design/submission.json) | [PR 7](https://github.com/sharonbasovich/performance_takehome/pull/7) | `cbfb5123d39d7849cc8ce8089aa197fd7339fe8c` |
| 2 — Optimization harness | [Delivery guide](tasks/harness-design/DELIVERY.md), [results and limitations](tasks/harness-design/NOTES.md), [manifest](tasks/harness-design/submission.json) | [PR 8](https://github.com/sharonbasovich/performance_takehome/pull/8) | `b87cf057672a05f5adfcb448c3cd1b62b8ac2da7` |
| 3 — Compute Quant | [Delivery and reproduction](tasks/compute-quant/DELIVERY.md), [decision memo](tasks/compute-quant/REPORT.md), [manifest](tasks/compute-quant/submission.json) | [PR 6](https://github.com/sharonbasovich/performance_takehome/pull/6) | `005888ef697f9f940ae743cb3e096e3a75706a4a` |
| 4 — Puzzle | [Public statement and answer format](tasks/puzzle-design/puzzle.md) | [PR 9](https://github.com/sharonbasovich/performance_takehome/pull/9) | `9deac7e6f6f4c505fab226f40f37a492e6e030f6` |

Task 4's complete solution, verifier, manifest and reports are retained for the
organizer's private delivery channel. Its public task branch contains the statement
and answer format only. The individual task PRs remain available for task-scoped review.

## Task 1: what the evidence establishes

The candidate-built suite includes measurement recording, independent timing checks,
fault/control fixtures, calibration and bounded execution. The original real
calibration, quick and full captures fit their recorded three-hour aggregate window.
Their source identities, failures and raw evidence remain preserved.

The original full capture lacks raw boundary-lag evidence needed to certify a later
recorder check. A separate current-recorder [90-request GPU diagnostic](tasks/benchmark-design/validation/engine-fixed90-supplemental-20261030/README.md)
retains complete raw streams and independently checked timings. It demonstrates the
specified delay at that tested point; it is not a full-suite revalidation, measured
power or an official grade. The original inconclusive results remain disclosed.

## Task 2: primary image and experiment provenance

The recommended `linux/amd64` image is:

```text
ghcr.io/sharonbasovich/performance_takehome-task2-llmd@sha256:84d13e8e4f6777ec4522d701d86e16181c0b170602a7e81db17dab7df525cabb
```

It uses batch size 4, selected by the documented controller-neighbor policy with
serial and small supplemental burst/long-input checks. The separate genuine
Pi-proposed batch-1 canonical experiment and its published image are retained as
experimental evidence. Their gains and selection attributions stay separate.
No result establishes that the new batch-1 image outperforms the recommended image.

The [delivery guide](tasks/harness-design/DELIVERY.md) provides the exact wrapper build,
complete runtime arguments, read-only model mount and verification commands. Both
images have retained anonymous full-layer verification and actual Docker pull/help
receipts. Weights are external and are not distributed in the images.

Configuration changes were possible with the supplied pinned binary. LLMD source
was unavailable, so engine source-level changes are not claimed. The successful Pi
run uses the declared one-response/no-tools overlay; the stock four-tool profile
remains a separately identified reference. Development results are local evidence;
Abstract's private evaluator supplies any official performance grade.

## Task 3: scope and reproduction

The runnable model, price curve, reservation valuation, scenarios and decision memo
use the supplied synthetic data. Dated observations, modeled estimates and assumptions
are distinguished. These fictional inputs support a reproducible demonstration, not
a real-market valuation claim. The [delivery guide](tasks/compute-quant/DELIVERY.md)
includes the independent cash-flow/source audit and fresh-output reproduction commands.

## Review and reproduce

Use a canonical LF checkout for recorded byte hashes. The task guides contain their
own CPU checks and optional live-run prerequisites. Reproducing model inference needs
the pinned model assets and the stated AMD GPU environment; reading reports and running
software checks does not require starting a cloud GPU or a coding-model API.

The externally recorded draft starter is
`81aead87d78ed468c4c374fb42921471b44c3f80`. Verify protected files with:

```sh
python -B -m tools.check_integrity --base 81aead87d78ed468c4c374fb42921471b44c3f80
```

The starter's root README and release policies are preserved. This review handoff
does not claim a released organizer profile, organizer acceptance or an official grade.
Historical capture/build commits remain the source of the recorded experiments;
later documentation and this combined branch do not change those source identities.
