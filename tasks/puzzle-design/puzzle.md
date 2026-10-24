# Puzzle: Two thousand numbers, no repeated gap

## Statement

Find a set **S** of integers such that

1. every element of S is an integer **x** with **0 ≤ x < 4,000,000**;
2. S contains **at least 2,000 distinct** integers;
3. **all pairwise differences are distinct**: whenever **a, b, c, d** are elements of S with
   **a > b**, **c > d**, and **(a, b) ≠ (c, d)**, then **a − b ≠ c − d**.

In words: no two *different* pairs of elements of S have the same gap between them.
(Equivalently, all sums **a + b** over unordered pairs of distinct elements **{a, b}** are
distinct.)

Nothing else is required. Any set that satisfies conditions 1–3 is a correct answer; there
is no unique intended answer.

## Conventions

- "Integer" means a plain JSON integer (no decimal point, no exponent, no quotes).
- The pairs in condition 3 are **unordered pairs of distinct elements**; the condition only
  constrains pairs where the two elements differ. A difference compares exactly two
  elements of S, and the same element may appear in many pairs.
- Order of the elements in your answer does not matter. Repeating an element is **not**
  allowed (the list must have no duplicates).
- Submitting more than 2,000 elements is allowed as long as conditions 1–3 still hold.

## Answer format

Your final answer must be a single JSON object with exactly one key, `"numbers"`, whose
value is a JSON array of the elements of S:

```json
{"numbers": [0, 1, 3]}
```

That example has the right *shape* only. It would **not** be accepted as an answer to this
puzzle because it has 3 elements, not at least 2,000. (It does satisfy condition 3: the
differences 1 − 0 = 1, 3 − 0 = 3, 3 − 1 = 2 are all distinct.)

Checked mechanically, in this order:

| check | rejected if |
|---|---|
| size | the answer is longer than 32 KiB (32,768 bytes) |
| syntax | the answer is not valid UTF-8 JSON, or the top-level value is not an object with exactly the one key `"numbers"`, or `"numbers"` is not an array |
| elements | any element is not a JSON integer, or is outside `0 ≤ x < 4000000` |
| count | fewer than 2,000 elements |
| distinct | two elements are equal |
| gaps | some difference `a − b` (with `a > b`) occurs for two different pairs |

Any answer passing every check is accepted. The checker is deterministic, uses only the
Python standard library, and tests the stated conditions directly — it does **not** compare
your answer against a stored answer.

## Limits

- Statement: this file.
- Final answer: at most 32 KiB. (2,000 seven-digit integers in the format above need
  roughly 18 KiB, so the limit is not a constraint for a straightforward answer.)
- You may use any tools you like; the puzzle is self-contained and needs no external data.
