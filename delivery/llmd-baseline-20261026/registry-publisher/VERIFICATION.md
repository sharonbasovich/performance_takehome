# Source verification — 26 October 2026

The final additive overlay passed all29 offline tests on Windows CPython3.13.3
and native Linux CPython3.14.4, with zero skips. Locked Ruff0.16.10 check and
format-check pass under the repository's existing configuration. Default real CLI
inspection returned `VALIDATED_NOT_UPLOADED`; no registry client was invoked.

Independent review checked the exact small OCI metadata, missing-attestation
closure, platform selection, strict destination/schema, workflow source gates and
exclusive/uncertain failure receipts. The final integration adds repository-style
formatting and exception chaining, qualified package-existence wording and local
Git attributes preserving raw image/selection bytes and LF source on Windows.
Earlier sealed source, failed probes and review receipts remain separate provenance.

These results exercise a closed fake registry and bounded local Python children.
They do not verify owner settings, package entitlement/visibility, large-layer
transfer, media acceptance, anonymous pull, inference, optimization or billing.
Workflow templates remain inactive and no publication approval marker is included.
