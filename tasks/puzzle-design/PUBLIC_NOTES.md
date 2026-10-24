# puzzle-design — public notes

Only `puzzle.md` (statement + answer format) is public. The private bundle — known-valid
answer, worked solution/proof, verifier, verifier tests, authoring log, report, `submission.json`
and all red-team / blind-test records — was delivered to the coordinator out of band as
`puzzle-design-private-bundle-v2.tar.gz` and is **not** in this repository or its history.

- Bundle SHA-256: `e9df24c14ce2a1df127788e5f5c0d61c69d9ee63d2493e1b288d4a00bc04d89d`
- Bundle size: 150,769 bytes (limit 256 KiB); statement 9,592 bytes (limit 16 KiB);
  known answer 9,612 bytes (limit 32 KiB).
- Frozen starter: commit `81aead87d78ed468c4c374fb42921471b44c3f80` (the draft release has no
  `takehome-start` tag).
- Authoring sessions were self-timed (no organizer clock exists in the draft); timestamps are in
  the private authoring log. The puzzle in `puzzle.md` replaces an earlier statement that a
  blind proxy solver broke quickly; the full record is in the private report.
- Resistance status (honest): not demonstrated — a fresh code-executing proxy session solved this
  statement in about 3 minutes; it was the longest holdout of five blind-tested candidates.

No hints about the solution are provided here or anywhere public.
