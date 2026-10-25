# Public notes — puzzle-design (Task 4)

The current candidate is **The stuttering carousel**. Only its statement/answer format
(`puzzle.md`) and these notes belong in the public tree. Its answer, proof, verifier,
construction, tests and full manifest remain private and ignored.

## Frozen local authoring attempt

This is an honest **candidate self-timed prototype**, not an organizer-timed submission.
No official Astra profile, authoritative organizer clock or private receipt was supplied.

- Start: 2026-10-24 18:45:45 UTC.
- Complete bundle frozen: 2026-10-24 19:01:17 UTC, **932 seconds / 15 minutes 32 seconds**.
- Local deadline: 2026-10-24 19:05:45 UTC.
- Transport receipt finalized at 19:02:14 UTC, also before the deadline.
- Frozen ZIP statement (CRLF line endings): 2,826 bytes; SHA-256
  `e364a36b193fbb0e3e5d241c0f9eb539a0012cc606091e09569abb2c5a526df1`.
- Public Git blob `puzzle.md` (LF line endings): 2,777 bytes; SHA-256
  `8eb9bd6005ef4a46711983b1a255d64945f9bff9e4a36f1be93ed35b9d479d7e`.
  Git's line-ending normalization removes the 49 carriage returns; normalizing the
  frozen statement from CRLF to LF gives exactly this public blob. A Windows checkout
  may restore CRLF. Use the frozen ZIP bytes for the authoring receipt and the Git blob
  bytes for a public-file hash check. The statement text, frozen ZIP and timed receipt
  have not been changed.
- Known answer: 8,036 bytes. Any valid strategy/equivalent leaf ordering is accepted.
- Complete private bundle: 109,702 uncompressed bytes / 19,346 ZIP bytes; both fit 256 KiB.
- ZIP: `codex-fresh-attempt.zip`; SHA-256
  `40ddb1719add97506a0393f31124423520cf2fb84757b075694ba84c04a14fe0`.

The private package contains the worked solution, deterministic stdin-only standard-library
Python verifier, eight tests, an independent physical simulation, construction source,
report and manifest. All eight tests passed for the author and were independently rerun.
The package was frozen before a fresh-context proxy solver received the statement. Neither
the statement nor private ZIP is changed in response to that later test.

**Resistance is not established.** A proxy experiment is separate from an official pinned
Astra run, and local timestamps are separate from organizer receipts. The bundle has not
been sent to the organizer. No official outcome is claimed.

After freeze, a fresh-context solver given only `puzzle.md` produced a different valid
strategy in **3 minutes 52 seconds** (19:04:22–19:08:14 UTC). The frozen verifier accepted
it. This candidate therefore has no demonstrated proxy resistance. The test did not
expose the private proof or verifier to that solver, and the frozen ZIP is unchanged.

## Preserved prior attempt

Devin's previous public statement, **The orthogonal mate** (order 50), remains in history
at `8e5249de2454e6c95d9697d96fe22ed9b9ce85e4`. Its private v4 bundle was attached to the Devin
coordinator handoff, recovered locally and hash-verified; it was not delivered to the
organizer. Every blind-tested prior candidate was solved in 20 seconds–3 minutes, and the
shipped prior instance had not met the timed-authoring requirement. Those limitations and
the earlier evidence are preserved, not attributed to this new instance.

No private answer/proof/verifier or hint-bearing candidate metadata is committed here.
