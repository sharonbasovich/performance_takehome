"""Private CPU-only measurement subprocess, bounded and terminated by the parent loop."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path[:0] = [str(HERE.parents[1]), str(HERE.parents[4])]

from abstract_harness import measure  # noqa: E402


def record_probe(trace: measure.RequestTrace) -> None:
    """Keep every startup attempt in the parent's separate stderr capture."""
    print(
        json.dumps({"event": "startup_probe", "trace": asdict(trace)}), file=sys.stderr, flush=True
    )


def main() -> int:
    payload = json.load(sys.stdin)
    operation = payload.pop("operation")
    if operation == "startup":
        result = measure.wait_for_first_valid_generation(**payload, on_probe=record_probe)
    elif operation == "benchmark":
        result = measure.run_benchmark(**payload).to_json()
    else:
        raise ValueError(f"unknown measurement operation {operation!r}")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
