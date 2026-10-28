# A dense sextic with two kinds of certificate

Find an exact short certificate that the following homogeneous polynomial is
nonnegative on R³ and is not a sum of squares of real polynomials.

For degree d, order exponent triples (a,b,c), a+b+c=d, by decreasing a and then
decreasing b. Thus the cubic order is

    x³, x²y, x²z, xy², xyz, xz², y³, y²z, yz², z³.

The target P is the degree-six polynomial with this coefficient vector in the
same order:

```text
[2194272, 368112, -10923768, 364357801, -369245757,
 340599099, -689506346, 1130661763, -1053458211, 747624746,
 311295385, -1816626909, 1145506683, -1805670453, 419381643,
 11195736, 1013220383, -1239453771, 1057379611, -1165618467,
 26443440, 1797696, 25203984, 1119910345, 691276010,
 1078087225, -44165880, 1342656]
```

The first seven sextic monomials are x⁶,x⁵y,x⁵z,x⁴y²,x⁴yz,x⁴z²,x³y³;
the last three are y²z⁴,yz⁵,z⁶. This convention specifies every coefficient.

## The mathematical certificate

Use the elementary templates

    T(A,B,C) = A⁴B² + A²B⁴ + C⁶ − 3A²B²C²,
    U(A,B,C) = A⁴B² + B⁴C² + C⁴A² − 3A²B²C².

For arbitrary real A,B,C, each is nonnegative: the first three nonnegative
terms have geometric mean A²B²C², so three-term AM–GM applies.

The first part of a certificate is an identity

    P = sum(i=1..r) w_i V_i(A_i,B_i,C_i) + sum(j=1..s) v_j q_j²,

where r≤2, s≤3, each V_i is T or U, all weights are strictly positive
rationals, A_i,B_i,C_i are arbitrary rational linear forms in x,y,z, and each
q_j is a rational homogeneous cubic. Degenerate or zero forms are permitted;
no coordinate map, factorization, or particular answer is prescribed.

The second part is 28 rational moments y_(a,b,c), in the sextic order. With
the ten cubic exponent triples α_i in the cubic order above, define

    M_ij = y_(α_i+α_j).

Require M to be positive semidefinite over the reals and require

    sum_(a+b+c=6) coefficient(P,x^a y^b z^c) · y_(a,b,c) < 0.

These requirements rule out every real SOS representation, with no bound on
its number of squares. The bounds r≤2 and s≤3 apply only to the submitted
nonnegativity identity.

Every scalar in the certificate must, after reduction to n/d with d>0,
satisfy |n|≤2⁶³−1 and d≤2⁶³−1. This is a compactness bound, not a requested
denominator or a hidden coordinate key. The supplied instance has a
certificate far below it. All exact certificates satisfying these stated
conditions are accepted.

## JSON submission

Submit one UTF-8 JSON object, at most 32768 bytes including whitespace:

```json
{
  "templates": [
    {"kind": "T", "weight": "1/2", "forms": [[1,0,0],[0,1,0],[0,0,1]]}
  ],
  "squares": [
    {"weight": 1, "coefficients": [0,0,0,0,1,0,0,0,0,0]}
  ],
  "moments": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
}
```

This is only a format example, not a valid answer. Each row of `forms` lists
the coefficients of x,y,z; each cubic vector and moment vector uses the order
specified above. `templates` may have zero through two entries, and `squares`
zero through three. Exactly the displayed object fields are allowed.

A rational is a JSON integer or a string matching
`[+-]?[0-9]+(?:/[+-]?[0-9]+)?`, with nonzero denominator. Equivalent unreduced
fractions and negative denominator strings are allowed; height is checked
after reduction. Floats, exponent notation, nonfinite values, booleans,
duplicate keys, extra fields, and malformed JSON are rejected.

Run the deterministic Python 3.11+ standard-library verifier as:

```text
python verify.py < answer.json
```

It prints one JSON result and returns exit status 0 exactly on acceptance.
It uses exact rational arithmetic throughout and does not compare against a
stored solution.
