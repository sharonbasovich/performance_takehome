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
that verifier is not part of the public fork or any blind trial's input.

## Four separate blind development trials

All four trials used a fresh `gpt-6.1-sol ultra` session with the same statement, Python,
installed packages, local shell, and clock. Network access, package installation,
delegation, private files, and correctness feedback were disallowed. These were
instruction-level workspace boundaries, not OS sandboxes. Each solver returned one
final answer. They were not official Astra runs, and no equivalence is claimed.

| Trial | Statement delivery | Hard receipt deadline | First parent-recorded final | Evaluation |
| --- | --- | --- | --- | --- |
| 1 | 00:35:02.051448 | 00:55:02.051448 | 00:55:09.572 | Exact identity invalid; parent record is 7.520552 seconds late. |
| 2 | 01:03:05.848606 | 01:23:05.848606 | 01:21:28.700 | Incomplete certificate; exact identity invalid; final recorded 97.148606 seconds before deadline. |
| 3 | 10:32:24 | 10:52:24 | 10:52:05 | Exact identity invalid; important near-complete numerical partial; 1,181 seconds elapsed and 19 seconds before deadline. |
| 4 (28 October) | 08:20:31.183947 | 08:40:31.183947 | 08:39:56.589236 | Incomplete positivity identity; exact non-SOS component valid; 1,165.405 seconds conservative elapsed upper bound. |

Trial 1's own metadata places its file write before the deadline, but the parent
log first records the final afterward. It is not presented as a confirmed on-time
receipt. Trial 2 is a separate fresh repeat that supplies a timely final and a
normal incomplete outcome. Both the independent exact checker and the frozen
author verifier rejected each final, with structured results and no checker timeout.
No grading feedback was sent back and no final was revised.

Parent timestamps identify the matching final-answer records, independently of
solver-created file timestamps. Their log format does not distinguish server
generation, transport arrival, and local serialization, so no exact network delay
or cryptographic time attestation is inferred.

**Demonstrated outcome:** trials 2, 3 and 4 returned no valid complete certificate
within their original 20-minute windows. Trial 3 reached an important near-complete
numerical positivity identity. Trial 4 independently passed the exact non-SOS
component but supplied no positivity decomposition. These are substantial partial
results, not valid complete exact certificates. Candidate 11 V2 remains the most supported local development
lead. These repeated proxy failures do not establish global hardness, satisfy an
unavailable official Astra profile, attest an OS sandbox, or earn an official grade.

Alternative development trials through 26 October 2026, 16:59 UTC, returned valid
mathematical answers within their original windows:

| Candidates | Independently accepted first-parent elapsed seconds, in order |
| --- | --- |
| 19–22 | 403, 451, 277, 253 |
| 23–27 | 259, 516, 691, 755, 837 |
| 30–37 | 243, 319, 204, 242, 305, 328, 120, 169 |

These are separate fresh development authors and statement/data/format-only blind
trials, not additional resistance results for candidate 11. Candidate 18 was also
solved, but its first-parent author clock was not retained. Attempts 28 and 29 failed
at agent dispatch or unsupported-model setup before producing a puzzle result;
infrastructure failures receive no resistance credit. Candidate 30 lacked an
original general-submission verifier. Candidate 37's actual answer passes every
mathematical rule, but later review found two frozen-verifier JSON contract defects:
a legal long integer in an ignored field is rejected, while an invalid non-finite
constant in an ignored field is accepted. No timed artifact was repaired afterward.
These limitations remain separate from the accepted mathematical answers.

Six further fresh development candidates were authored and tested on 28 October
2026. Each author received a new 20-minute window and delivered a complete frozen
bundle before its original deadline. Post-author independent checks confirmed a
valid answer and alternative answers; those later checks are not timed authorship.
Each blind solver received only its candidate's statement, data and answer format,
under the same development profile described above.

| Candidate | Blind dispatch (UTC) | Original deadline (UTC) | First parent-recorded final (UTC) | Conservative elapsed upper bound | Exact grade |
| --- | --- | --- | --- | --- | --- |
| 43 | 06:24:00.5886355 | 06:44:00.5886355 | 06:27:03.6932392 | 183.105 seconds | Valid complete answer |
| 44 | 06:44:25.5786942 | 07:04:25.5786942 | 06:48:12.6992388 | 227.121 seconds | Valid complete answer |
| 45 | 07:32:20.9162628 | 07:52:20.9162628 | 07:35:12.4517193 | 171.535 seconds | Valid complete answer |
| 46 | 08:04:14.4316651 | 08:24:14.4316651 | 08:12:28.6221248 | 494.190 seconds | Valid complete answer |
| 47 | 08:40:07.481241 | 09:00:07.481241 | 08:43:09.114070 | 181.633 seconds | Valid complete answer |
| 48 | 09:01:37.298182 | 09:21:37.298182 | 09:04:25.623783 | 168.326 seconds | Valid complete answer |

All six original finals passed their frozen verifiers and separate exact constraint
checks. No trial received correctness feedback or revised its final. The
elapsed bounds include dispatch and parent recording; they are not an assertion
of exact generation or network time. All six candidates were solved on time and earn
no resistance credit in these proxy trials. Candidate 11 V2 remains the strongest
supported local lead. Their private construction, proofs, verifiers and trial
workspaces remain outside public Git; no official Astra result is claimed.

Candidate 48 encountered a model-capacity interruption during authorship and
resumed with its existing context inside the same original window. Its archive
froze at 09:00:12.669738 and its completed author final was parent-recorded at
09:00:41.146272, before the unchanged 09:03:09.124264 deadline. No new author
window, external mathematical feedback or live solver test was supplied. This
infrastructure recovery is retained in the private provenance.

## Packaging and protocol limits

The immutable timed author ZIP and its manifests are separate from the later
administrative handoff, evaluation receipts, and public Git update. Later packaging
and review time is not counted as work completed inside the original 20 minutes.
The public manifest distinguishes frozen CRLF statement bytes from Git's LF blob;
their text is identical after newline normalization.

A later private organizer-core ZIP is 15,686 bytes with 13 members (32,950 bytes
uncompressed), below the draft 256 KiB bundle limit. With the unchanged 2,593-byte
statement-only ZIP, the two archives total 18,279 bytes. The core preserves the
original statement, polynomial, known answer, proof, verifier and selected provenance
byte for byte; new administrative notes disclose their scope. The complete 698,863-byte
trial/audit history remains separate. This reduces administrative delivery size only;
it does not create a new timed author artifact or establish official conformance.
The exact known answer is 1,809 bytes and fits the draft 32 KiB answer cap.

The starter protocol is a draft. This statement permits 65,536 answer bytes, whereas
the draft proposes 32 KiB. The original verifier takes an answer filename, whereas
the draft proposes stdin. A separately labelled, later administrative stdin adapter
is retained separately in the full private audit handoff; it preserves the exact
mathematical checks and is not
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
