# The stuttering carousel

A carousel has thirteen positions, numbered 0 through 12 clockwise. Exactly two
identical markers occupy two distinct positions. Their **initial unordered pair of
positions** is hidden. You must identify that initial pair.

You can repeatedly choose a clockwise rotation by an integer `d` from 1 through
12. Every marker then moves from position `x` to `(x+d) mod 13`. Rotation is exact;
the position numbers and the sensor stay fixed. After each rotation you receive
one bit from a sensor:

* Its truthful bit is **1 if exactly one** marker is at a position in
  `{1,3,5,8,9,11}`, and **0 otherwise** (including when both markers are there).
* Over the entire experiment, **at most one received bit may be inverted**.
  The inversion can occur on any reading and can be chosen adversarially after
  seeing your choices. Every other received bit is truthful. There may be no
  inversion.

There is no initial sensor reading. You may choose each rotation using all the
bits received so far, and you may stop early. Rotations may be repeated. You do
not see either marker, and you receive no other information.

**Find a strategy that always identifies the initial pair using at most ten
rotations/readings.** As a further reasoning question, explain why nine can never
suffice, even if rotations by zero and any additional sensor patterns were allowed.
The submitted structured answer contains the strategy only; the explanation is
for your own reasoning and is not part of the machine-checked answer.

## Answer format

Submit one UTF-8 JSON object with exactly the key `strategy`. Its value is a finite
binary decision tree, recursively encoded as follows:

* A leaf is `[a,b]`, where `a` and `b` are distinct JSON integers from 0 through
  12. It declares that the initial positions were `{a,b}`. Either order is accepted.
* An internal node is `[d,zero,one]`, where `d` is a JSON integer from 1 through
  12 and `zero` and `one` are decision trees. Rotate by `d`, read the possibly
  inverted bit, then follow `zero` for a received 0 or `one` for a received 1.

Every root-to-leaf path must contain at most ten internal nodes. All branches
must have the stated syntax, including branches that cannot be reached. A leaf
on an unreachable branch may name any distinct pair. JSON booleans, fractional
numbers, duplicate object keys, extra keys and trailing non-whitespace text are
not part of the format. Whitespace is immaterial. The complete answer must be at
most 32,768 bytes. Any strategy satisfying these rules and succeeding for every
initial pair and every allowed inversion is accepted.

For example, `{"strategy":[4,[0,1],[2,3]]}` illustrates the encoding: rotate by 4
and declare one of two pairs. It is **not** a solution to this puzzle.
