"""On-disk harness state (JSON) so an interrupted run resumes from where it stopped."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATE_SCHEMA_VERSION = 1


@dataclass
class ImageRef:
    """A built image the harness knows about."""

    tag: str
    digest: str
    image_id: str | None = None
    experiment: str = ""
    report: str = ""
    patch: str = ""


@dataclass
class InProgress:
    """Marker for the attempt currently executing (used to log interruptions on resume)."""

    experiment: str
    hypothesis: str
    started_ts: float
    patch_path: str
    stage: str = "proposed"
    container: str = ""
    image_tag: str = ""


@dataclass
class HarnessState:
    """Everything the loop needs to resume: last-good image, baseline samples, ledgers."""

    schema_version: int = STATE_SCHEMA_VERSION
    engine: str = ""
    source_commit: str = ""
    lease_start_ts: float = 0.0
    attempt_index: int = 0
    api_usd_cumulative: float = 0.0
    last_good: ImageRef | None = None
    baseline_samples: dict[str, Any] = field(default_factory=dict)
    golden: dict[str, str] = field(default_factory=dict)
    in_progress: InProgress | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    finish_reason: str = ""

    def to_json(self) -> dict[str, Any]:
        """Plain-dict form."""
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> HarnessState:
        """Rebuild from :meth:`to_json` output; unknown keys are ignored."""
        if data.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported state schema {data.get('schema_version')!r}")
        last_good = data.get("last_good")
        in_progress = data.get("in_progress")
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {
            k: v for k, v in data.items() if k in known and k not in {"last_good", "in_progress"}
        }
        state = cls(**kwargs)
        state.last_good = ImageRef(**last_good) if last_good else None
        state.in_progress = InProgress(**in_progress) if in_progress else None
        return state


def load_state(path: Path) -> HarnessState | None:
    """Load state or return ``None`` when no state exists yet."""
    if not path.exists():
        return None
    return HarnessState.from_json(json.loads(path.read_text(encoding="utf-8")))


def save_state(path: Path, state: HarnessState) -> None:
    """Atomically persist state (write temp file, fsync, rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state.to_json(), fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def utc_ts(now: float | None = None) -> str:
    """ISO-8601 UTC timestamp with seconds precision."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))
