"""Validate an explicit reviewed branch marker before registry login. No network."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPOSITORY = "sharonbasovich/performance_takehome"
REF = "refs/heads/codex/task2-registry-publish-approved"


def check(root, repository, ref):
    root = Path(root)
    if repository != REPOSITORY or ref != REF:
        raise ValueError("wrong repository/explicit publication branch")
    raw = (root / "evidence/PUBLICATION_APPROVAL.json").read_bytes()
    if not 0 < len(raw) <= 16384:
        raise ValueError("bounded explicit approval marker required")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate approval key")
            out[key] = value
        return out

    p = json.loads(raw, object_pairs_hook=pairs)
    required = {
        "repository",
        "ref",
        "selection_sha256",
        "publisher_sha256",
        "checker_sha256",
        "execute_workflow_sha256",
        "acknowledge_baseline_fallback",
        "acknowledge_private_package_access_pending",
    }
    if (
        set(p) != required
        or p["repository"] != repository
        or p["ref"] != ref
        or p["acknowledge_baseline_fallback"] is not True
        or p["acknowledge_private_package_access_pending"] is not True
    ):
        raise ValueError("exact reviewed approval contract required")
    for field, path in [
        ("selection_sha256", root / "evidence/selection.json"),
        ("publisher_sha256", root / "src/publish_baseline_config_only.py"),
        ("checker_sha256", root / "src/check_publication_approval.py"),
        ("execute_workflow_sha256", root / "workflow/execute-baseline-config-only.yml"),
    ]:
        if (
            not re.fullmatch("[0-9a-f]{64}", p[field])
            or path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != p[field]
        ):
            raise ValueError("approval file identity mismatch")
    actual = root.parent / ".github/workflows/execute-baseline-config-only.yml"
    if (
        actual.is_symlink()
        or hashlib.sha256(actual.read_bytes()).hexdigest() != p["execute_workflow_sha256"]
    ):
        raise ValueError("running workflow differs from reviewed copy")
    return p["selection_sha256"]


if __name__ == "__main__":
    try:
        print(
            check(
                Path(sys.argv[1]),
                os.environ.get("GITHUB_REPOSITORY", ""),
                os.environ.get("GITHUB_REF", ""),
            )
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit("REFUSED: " + str(exc)) from exc
