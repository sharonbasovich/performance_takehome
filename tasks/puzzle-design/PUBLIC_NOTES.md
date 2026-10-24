# Public notes — puzzle-design (Task 4)

Only `puzzle.md` (the statement, "The orthogonal mate", order 50) and this file are public. The
solution, proof, verifier, verifier tests, REPORT.md, submission.json, authoring log, candidate
files and all attack / blind-solver evidence are delivered privately to the organizer as
`puzzle-design-private-bundle-v3.tar.gz` and are **not** in this repository or its history
(audited from a clean clone: `git log --all --name-only -- tasks/puzzle-design` lists only the
organizer files, `puzzle.md` and `PUBLIC_NOTES.md`).

## Private bundle v3
- File: `puzzle-design-private-bundle-v3.tar.gz`
- SHA-256: `35ef90dc44380aecbc41bd9b7e42a9d1d5673363f3c5c51dd510301766327a21`
- Compressed size: 204,313 bytes. The archive root is `.private/`, so unpack with
  `tar -xzf puzzle-design-private-bundle-v3.tar.gz -C tasks/puzzle-design`
  (not `-C tasks/puzzle-design/.private`).
- Size accounting (bundle `sizes.txt`): statement 9,822 B (limit 16 KiB); known answer 9,612 B
  (limit 32 KiB); core submission set (statement + answer + SOLUTION.md + verify.py + tests +
  submission.json + REPORT.md + AUTHORING_LOG.md) 67,605 B and the compressed archive 204,313 B are
  both under 256 KiB; the full uncompressed `.private/` tree including all prior-candidate and
  attack evidence is 669,045 B and exceeds 256 KiB — the 256 KiB claim is made only for the core set
  and the compressed archive.
- Supersedes bundle v2 (SHA-256 `e9df24c1…d89d`), which was found by an independent review to be
  missing four blind-solver artifacts and to contain count/wording errors (fixed in v3, REPORT §15).

## Honesty statements
- **Resistance claim: not demonstrated.** Every candidate that was blind-tested (five, including
  the shipped puzzle) was solved by a fresh code-executing session given only the statement, in
  20 s – 3 min; the shipped puzzle is the longest holdout (3.0 min). Solver reports and answers are
  in the private bundle (`blind/`), each re-verified with the matching verifier.
- **Timed-authoring requirement: not met as specified.** The shipped instance was authored outside
  the clock during candidate generation; the self-timed "Phase B #2" window only promoted
  precomputed files. The clock log for the first session (a rejected candidate) is honest and
  included in the private authoring log. No session was backdated.
- An independent reviewer produced a second valid answer from `puzzle.md` alone in 16 s; the
  verifier accepts it (the verifier is property-based and accepts every valid answer, not a stored
  one).
- The verifier is deterministic, standard-library only, reads only stdin, and was tested with 28
  contract / fuzz / adversarial cases under RLIMIT_AS 256 MiB and RLIMIT_CPU 2 s (worst case 0.021 s,
  11.6 MiB; measurements in the bundle).
- Timestamps are the authoring VM's clock (UTC); no organizer clock, Astra profile, receipt or
  official solver run exists in this draft.
- Starter commit `81aead87d78ed468c4c374fb42921471b44c3f80` (no `takehome-start` tag exists);
  protected organizer files are unchanged (integrity check PASS from a clean clone).
- GitHub Actions is not enabled on this fork, so the PR shows no checks; the root checks (ruff,
  40 unit tests, `uv build`, integrity) were run from a clean clone and their output is in the bundle.
