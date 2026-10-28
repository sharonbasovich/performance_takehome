# Public evaluation and provenance — Task 4

The current local development lead is **A dense sextic with two kinds of certificate** (candidate 53). The selection follows three clean timely incomplete development trials and completed quality review. It is a local comparative decision, not an official score or a claim of universal hardness. The proposed public artifacts are only `puzzle.md`, these notes, and `PUBLIC_MANIFEST.json`. The answer, proof, verifier, construction, test code, and solver workspaces remain private.

Candidate 11 V2 remains preserved in Git history. Its preceding public statement and notes are permanently addressable at [the C11 statement](https://github.com/sharonbasovich/performance_takehome/blob/c8c873f002d8ba24f9c66a6e4913c8e323d8544a/tasks/puzzle-design/puzzle.md) and [the C11 evaluation record](https://github.com/sharonbasovich/performance_takehome/blob/c8c873f002d8ba24f9c66a6e4913c8e323d8544a/tasks/puzzle-design/PUBLIC_NOTES.md). This selection does not erase that development history. The prior public head is `c8c873f002d8ba24f9c66a6e4913c8e323d8544a`.

## Original author interval and immutable freeze

All times are UTC on 28 October 2026. The unchanged original author window was **09:58:39.295998–10:18:39.295998**. Self-completion was recorded at **10:14:02.619735** and the first parent-recorded completed author final at **10:16:39.917314**, both before the deadline. The original completed mathematical/parser package needed no corrective successor from independent QA. The later administrative adapter described below is separate.

The original private frozen archive is **35,728 bytes**, SHA-256 `adf2c5792f7a341ba4fcd55c9cfb996e6757bd5b72f9b2cc096df509df7fdc95`, and remains byte-for-byte unchanged. Its private contents include the complete answer and supporting evidence; the archive is not a public deliverable. The public statement is copied from the original with only CRLF-to-LF normalization for Git. The statement defines the full task; its attached-verifier reference refers to the private handoff, not a public code attachment.

## Four separate statement-only proxy trials

These were fresh `gpt-6.1-sol` sessions at `ultra` reasoning with the same frozen statement, Python/installed packages, local shell, and clock. Network access, installations, further delegation, private solution material, and correctness feedback were disallowed. Boundaries were instruction-level, not OS sandboxes. They are development proxies, not the unavailable official Astra profile. Each original maximum window and original final were preserved without feedback-driven revision or extension.

Elapsed values below are conservative dispatch-clock-start to first-parent-recorded-final upper bounds, rounded upward to one millisecond. Start times identify the recorded original window, rather than attesting exact server delivery. Parent records do not distinguish generation, transport arrival, and serialization; no exact network-delay or cryptographic time-attestation claim is made.

| Trial | Original clock start | Unchanged deadline | First parent-recorded final | Elapsed upper seconds, rounded up | Outcome |
| --- | --- | --- | --- | ---: | --- |
| 1 | 10:18:15.524929 | 10:38:15.524929 | 10:37:48.029474 | 1172.505 | Clean timely incomplete |
| 2 | 10:40:12.064509 | 11:00:12.064509 | 10:59:12.857096 | 1140.793 | Timely incomplete; dispatch-confounded, excluded |
| 3 | 11:01:50.852826 | 11:21:50.852826 | 11:21:05.895960 | 1155.044 | Clean timely incomplete |
| 4 | 11:21:23.711528 | 11:41:23.711528 | 11:40:30.628343 | 1146.917 | Clean timely incomplete |

Trials **1, 3, and 4** form the three clean timely incomplete results used for selection. Each passed the exact non-SOS moment component but lacked the required compact positivity identity. These are substantial mathematical partial results. They do not show inability to prove the broader claims by any method: the published task specifically requires the stated short certificate. Trial 1 also retained a broader exact positivity identity outside the allowed square count; it is not a qualifying complete answer.

Trial **2** is excluded from clean full-window resistance evidence. Its recorded start was 10:40:12.064509, but the actual spawn was bounded between 10:43:14 and 10:44:37.032421, while the original 11:00:12.064509 deadline remained unchanged. Its timely incomplete outcome is retained transparently, without counting it as another clean full-window result.

## Independent quality review and interface boundary

Independent untimed, witness-informed review passed **54 certificate/parser cases**, **759 exhaustive small symmetric PSD comparisons**, and **24 bounded resource runs**. It checked exact statement/verifier correspondence, alternative representations, full singular-PSD acceptance, long legal unreduced fractions, malformed data, byte limits, standard-library execution, and archive integrity. No blocking correctness, parser, or fairness defect was found. Observed resource probes were within the draft limits; they are not a guarantee on every host or an OS sandbox attestation.

The original frozen verifier natively reads stdin and enforces a **32 KiB (32768-byte)** answer limit. Its original output is `accepted` with `pairing` on success or `reason` on rejection. The draft starter proposes `valid` and `reason`, so the immutable original has an output-schema gap against that draft.

An **optional later administrative adapter** checks an exact copy of the original checker and changes only the output interface to `valid` and `reason`. It is separate from the timed freeze. Nine parent CLI equivalence checks and six independent actual CLI equivalence checks passed, including singular PSD and the exact byte limit. Neither the adapter nor this documentation is original timed author work, official protocol approval, organizer upload, or official conformance. Final organizer requirements remain controlling.

Compared with C11 V2, C53 has cleaner original authoring/parser provenance and closer native stdin/32-KiB interface fit. C11 V2 transparently required a parent-QA-identified long-integer parser correction within its author interval and remains valid development history. These distinctions, the completed review, and the three clean proxy incompletes support the current local selection; none alone establishes official resistance.

## Recent alternative development results

Candidates 43–52 were all solved with independently accepted original finals within their original windows. Their conservative first-parent elapsed upper bounds are rounded upward to one millisecond. They receive no resistance credit from these runs.

| Candidate | Elapsed upper seconds, rounded up | Outcome |
| --- | ---: | --- |
| 43 | 183.105 | Solved timely; no resistance credit |
| 44 | 227.121 | Solved timely; no resistance credit |
| 45 | 171.536 | Solved timely; no resistance credit |
| 46 | 494.191 | Solved timely; no resistance credit |
| 47 | 181.633 | Solved timely; no resistance credit |
| 48 | 168.326 | Solved timely; no resistance credit |
| 49 | 229.970 | Solved timely; no resistance credit |
| 50 | 362.823 | Solved timely; no resistance credit |
| 51 | 87.537 | Solved timely; no resistance credit |
| 52 | 249.540 | Solved timely; no resistance credit |

Earlier development history remains in the preserved C11 record. These alternative results are separate candidate runs, not extra C53 trials.

No official Astra profile identity/hash is available, no organizer private upload has occurred, and no official grade, profile equivalence, global-hardness claim, or exact network-timing claim is asserted. The private handoff is retained for review and delivery when authorized.
