# Public evaluation and provenance — Task 4

The current candidate is **A compact positivity certificate beyond sums of squares**
(candidate 11, V2). The public deliverables are `puzzle.md`, these non-solution-bearing
notes, and `PUBLIC_MANIFEST.json`. The answer, worked proof, verifier, construction
source, test cases, and blind-run workspaces remain in the separate private handoff.

This is a candidate-run development exercise. No official Astra profile, organizer
clock, private-upload receipt, or official result is asserted. The private handoff
is prepared for review and has not been delivered to the organizer.

## Authoring and freeze

All times below are UTC. The fresh author interval was **2026-10-26 00:02:04 through
00:22:04**, with no extension. The author used `gpt-6.1-sol` at `ultra` reasoning and
Python. No live solver trial occurred during authoring. Earlier candidates are
development history, not results for this instance.

V1 froze at 00:11:30. Independent pre-blind QA then found that Python's default
decimal integer-conversion limit rejected some legal, long, unreduced fractions.
That was a verifier defect. The author received external QA feedback within the
original interval and produced V2 in a new directory; V1 remains unchanged. V2
removes that interpreter limit after enforcing the stated input-byte cap. Its
statement, polynomial, answer, and mathematical acceptance conditions are unchanged
from V1. This was a successor with external QA, rather than an unaided single freeze.

The V2 sealing record is **00:19:01.406784**. Its declared conservative freeze boundary
is **00:20:00**, not an exact observed write time. The recorded post-freeze author
and parent clock observations were 00:20:10 and 00:20:23, before the original deadline.
The frozen author package includes 42 ordinary tests, 11 isolated parser tests, a
worked proof, and exact algebra checks. Later independent review confirmed the
known answer and valid alternatives, including a legal 65,536-byte answer, and
rejected malformed cases. The original frozen package is retained byte for byte.

The statement is sufficient to define the mathematical task and answer format.
Its reference to an attached verifier refers to the private organizer handoff;
that verifier is not part of the public fork or either blind solver's input.

## Two separate blind development trials

Both trials used a fresh `gpt-6.1-sol ultra` session with the same statement, Python,
installed packages, local shell, and clock. Network access, package installation,
delegation, private files, and correctness feedback were disallowed. These were
instruction-level workspace boundaries, not OS sandboxes. Each solver returned one
final answer. They were not official Astra runs, and no equivalence is claimed.

| Trial | Statement delivery | Hard receipt deadline | First parent-recorded final | Evaluation |
| --- | --- | --- | --- | --- |
| 1 | 00:35:02.051448 | 00:55:02.051448 | 00:55:09.572 | Exact identity invalid; parent record is 7.520552 seconds late. |
| 2 | 01:03:05.848606 | 01:23:05.848606 | 01:21:28.700 | Incomplete certificate; exact identity invalid; final recorded 97.148606 seconds before deadline. |

Trial 1's own metadata places its file write before the deadline, but the parent
log first records the final afterward. It is not presented as a confirmed on-time
receipt. Trial 2 is a separate fresh repeat that supplies a timely final and a
normal incomplete outcome. Both the independent exact checker and the frozen
author verifier rejected each final, with structured results and no checker timeout.
No grading feedback was sent back and neither final was revised.

Parent timestamps identify the matching final-answer records, independently of
solver-created file timestamps. Their log format does not distinguish server
generation, transport arrival, and local serialization, so no exact network delay
or cryptographic time attestation is inferred.

**Demonstrated outcome:** the second development proxy returned no valid answer
within its allowed trial. One unsuccessful proxy run does not establish universal
resistance, satisfy an unavailable official profile, or earn an official grade.

## Packaging and protocol limits

The immutable timed author ZIP and its manifests are separate from the later
administrative handoff, evaluation receipts, and public Git update. Later packaging
and review time is not counted as work completed inside the original 20 minutes.
The public manifest distinguishes frozen CRLF statement bytes from Git's LF blob;
their text is identical after newline normalization.

The starter protocol is a draft. This statement permits 65,536 answer bytes, whereas
the draft proposes 32 KiB. The original verifier takes an answer filename, whereas
the draft proposes stdin. A separately labelled, later administrative stdin adapter
is included privately; it preserves the exact mathematical checks and is not
relabeled as part of the timed authoring artifact. Official profile, runner, size,
and private-upload conformance remain subject to organizer validation.

## Preserved history

The prior public candidate, **The stuttering carousel**, remains at
`9d16ef17d9833f9d23bd8f3dcf9c4ff57125f639`. A fresh proxy solved it in 3 minutes
52 seconds; it has no demonstrated proxy resistance. Earlier prototypes, including
the order-50 orthogonal-mate candidate, remain in Git history and private audit
records. Their results are not attributed to candidate 11.

Protected starter materials remain based on
`81aead87d78ed468c4c374fb42921471b44c3f80`. This update contains no private answer,
proof, verifier, construction, solver transcript, or experiment script.
