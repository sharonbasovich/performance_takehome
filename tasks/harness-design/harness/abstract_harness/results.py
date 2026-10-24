"""Exact `results.tsv` schema, outcome vocabulary, escaping, and append/read helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, fields
from pathlib import Path

COLUMNS: tuple[str, ...] = (
    "ts",
    "experiment",
    "source_commit",
    "image_digest",
    "kept",
    "outcome",
    "local_ttft_speedup",
    "local_ftgr_speedup",
    "local_startup_s",
    "api_usd_cumulative",
    "gpu_hours_cumulative",
    "hypothesis",
    "notes",
    "development_report",
    "patch_path",
)

OUTCOMES: frozenset[str] = frozenset(
    {"baseline", "improved", "no_change", "regressed", "gate_failed", "error", "interrupted"}
)
KEPT_VALUES: frozenset[str] = frozenset({"0", "1"})
HEADER_LINE = "\t".join(COLUMNS) + "\n"

_ESCAPES = {"\\": "\\\\", "\t": "\\t", "\n": "\\n", "\r": "\\r"}


class ResultsError(ValueError):
    """Raised when a row or file violates the results.tsv contract."""


def escape_field(value: str) -> str:
    """Escape tabs/newlines/backslashes so a field stays on one TSV line."""
    return "".join(_ESCAPES.get(ch, ch) for ch in value)


def unescape_field(value: str) -> str:
    """Reverse :func:`escape_field`."""
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            mapped = {"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}.get(nxt)
            if mapped is not None:
                out.append(mapped)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def format_metric(value: float | None, digits: int = 4) -> str:
    """Format an optional metric; ``None`` becomes blank (blank is never zero)."""
    if value is None:
        return ""
    if value != value or value in (float("inf"), float("-inf")):
        return ""
    return f"{value:.{digits}f}"


@dataclass(frozen=True)
class ResultRow:
    """One attempt row. Every field is a string exactly as written to the TSV."""

    ts: str
    experiment: str
    source_commit: str
    image_digest: str
    kept: str
    outcome: str
    local_ttft_speedup: str = ""
    local_ftgr_speedup: str = ""
    local_startup_s: str = ""
    api_usd_cumulative: str = ""
    gpu_hours_cumulative: str = ""
    hypothesis: str = ""
    notes: str = ""
    development_report: str = ""
    patch_path: str = ""

    def validate(self) -> None:
        """Raise :class:`ResultsError` if the row violates the contract."""
        if self.outcome not in OUTCOMES:
            raise ResultsError(f"outcome {self.outcome!r} not in {sorted(OUTCOMES)}")
        if self.kept not in KEPT_VALUES:
            raise ResultsError(f"kept must be '0' or '1', got {self.kept!r}")
        if not self.ts or not self.experiment or not self.source_commit:
            raise ResultsError("ts, experiment and source_commit are required")
        if self.kept == "1":
            if not self.image_digest.startswith("sha256:"):
                raise ResultsError("a kept row must carry a resolved sha256 image digest")
            if not self.development_report:
                raise ResultsError("a kept row must reference its development report")
            if self.outcome not in {"baseline", "improved"}:
                raise ResultsError(f"outcome {self.outcome!r} cannot be kept")
        if self.image_digest and not self.image_digest.startswith("sha256:"):
            raise ResultsError(
                f"image_digest must be blank or sha256:..., got {self.image_digest!r}"
            )
        for name in ("local_ttft_speedup", "local_ftgr_speedup", "local_startup_s"):
            value = getattr(self, name)
            if value != "":
                try:
                    float(value)
                except ValueError as exc:
                    raise ResultsError(f"{name} must be blank or numeric") from exc
        for name in ("api_usd_cumulative", "gpu_hours_cumulative"):
            value = getattr(self, name)
            if value != "" and float(value) < 0:
                raise ResultsError(f"{name} cannot be negative")
        for f in fields(self):
            raw = getattr(self, f.name)
            if any(ch in raw for ch in "\t\n\r"):
                raise ResultsError(f"field {f.name} contains an unescaped control character")

    def to_line(self) -> str:
        """Serialize to one TSV line (fields are escaped, trailing newline included)."""
        return "\t".join(getattr(self, c) for c in COLUMNS) + "\n"

    @classmethod
    def from_line(cls, line: str) -> ResultRow:
        """Parse one TSV line (without unescaping; fields stay as written)."""
        parts = line.rstrip("\n").split("\t")
        if len(parts) != len(COLUMNS):
            raise ResultsError(f"expected {len(COLUMNS)} columns, found {len(parts)}")
        return cls(**dict(zip(COLUMNS, parts, strict=True)))


def make_row(**values: str) -> ResultRow:
    """Build a validated row, escaping every free-text field."""
    escaped = {k: escape_field(v) for k, v in values.items()}
    row = ResultRow(**escaped)
    row.validate()
    return row


def ensure_header(path: Path) -> None:
    """Create ``path`` with the exact header if it is missing or empty."""
    if path.exists() and path.stat().st_size > 0:
        with path.open("r", encoding="utf-8") as fh:
            first = fh.readline()
        if first != HEADER_LINE:
            raise ResultsError(f"{path} has an unexpected header: {first!r}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER_LINE, encoding="utf-8")


def repair_torn_tail(path: Path) -> str | None:
    """Cut off a partial last line (no trailing newline) left by a torn write.

    The fragment is appended to ``<path>.torn`` for forensics and returned;
    ``None`` when the file is absent or intact.
    """
    if not path.exists():
        return None
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return None
    cut = data.rfind(b"\n") + 1
    torn = data[cut:]
    with path.with_suffix(path.suffix + ".torn").open("ab") as fh:
        fh.write(torn + b"\n")
    with path.open("r+b") as fh:
        fh.truncate(cut)
        fh.flush()
        os.fsync(fh.fileno())
    return torn.decode("utf-8", "replace")


def append_row(path: Path, row: ResultRow) -> None:
    """Validate then append one row; the write is flushed and fsynced.

    A torn partial last line from an earlier crash is removed first (see
    :func:`repair_torn_tail`) so the new row never gets glued onto it.
    """
    row.validate()
    repair_torn_tail(path)
    ensure_header(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(row.to_line())
        fh.flush()
        os.fsync(fh.fileno())


def iter_rows(path: Path) -> Iterator[ResultRow]:
    """Yield validated rows from an existing results file."""
    with path.open("r", encoding="utf-8") as fh:
        header = fh.readline()
        if header != HEADER_LINE:
            raise ResultsError(f"{path} has an unexpected header: {header!r}")
        for number, line in enumerate(fh, start=2):
            if not line.strip():
                continue
            if not line.endswith("\n"):
                raise ResultsError(f"{path}:{number}: truncated last line (no trailing newline)")
            row = ResultRow.from_line(line)
            try:
                row.validate()
            except ResultsError as exc:
                raise ResultsError(f"{path}:{number}: {exc}") from exc
            yield row


def read_rows(path: Path) -> list[ResultRow]:
    """Read and validate every row of a results file."""
    return list(iter_rows(path))


def validate_file(path: Path) -> list[ResultRow]:
    """Validate the whole file including ordering rules; return the rows."""
    rows = read_rows(path)
    if rows and rows[0].outcome != "baseline":
        raise ResultsError("first row must be the baseline")
    for row in rows[1:]:
        if row.outcome == "baseline":
            raise ResultsError("only the first row may be the baseline")
    return rows
