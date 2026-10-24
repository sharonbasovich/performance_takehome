"""Proposers: produce one experiment (hypothesis + unified-diff patch) per attempt.

* :class:`ScriptedProposer` - deterministic queue read from a JSON file; used
  for tests, for the stand-in evidence run, and whenever no coding-model key is
  present. Its patches are real unified diffs generated with ``difflib``.
* :class:`PiProposer` - launches the pinned Pi 1.0.0 coding agent
  (``@earendil-works/pi-coding-agent@1.0.0``) non-interactively (``--print``)
  in an isolated, task-scoped agent directory with exactly the tools and
  isolation flags from ``agent-harness/profiles.json`` / ``agent-harness/README.md``
  and extracts the single patch it writes.

API keys are only ever read from environment variables and are never written
to any log, report, or transcript produced here.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import procs

PI_PACKAGE = "@earendil-works/pi-coding-agent"
PI_VERSION = "1.0.0"
PI_STOCK_TOOLS: tuple[str, ...] = ("read", "bash", "edit", "write")
PI_ISOLATION_FLAGS: tuple[str, ...] = (
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
    "--no-approve",
)
SECRET_ENV_PATTERN = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)


class ProposerError(RuntimeError):
    """A proposer could not produce a usable proposal.

    ``api_usd`` carries any model spend that happened before the failure so the
    loop can still account for it.
    """

    def __init__(self, message: str, *, api_usd: float | None = None) -> None:
        super().__init__(message)
        self.api_usd = api_usd


@dataclass(frozen=True)
class Proposal:
    """One experiment to try: a hypothesis and a unified diff against the build context."""

    experiment: str
    hypothesis: str
    patch: str
    notes: str = ""
    api_usd: float = 0.0
    transcript_path: str = ""


@dataclass
class ProposerContext:
    """What a proposer may read to decide on the next experiment."""

    program_md: str
    profile: Mapping[str, Any]
    history: Sequence[Mapping[str, Any]]
    context_dir: Path
    work_dir: Path
    engine: str
    budget_summary: str = ""


class Proposer:
    """Base class."""

    name = "base"

    def propose(self, context: ProposerContext) -> Proposal | None:
        """Return the next proposal or ``None`` when the proposer has nothing left."""
        raise NotImplementedError


def unified_diff_for_dirs(old_dir: Path, new_dir: Path) -> str:
    """Unified diff (``a/`` / ``b/`` prefixes, applies with ``patch -p1``) between two trees."""
    chunks: list[str] = []
    files = sorted(
        {p.relative_to(old_dir) for p in old_dir.rglob("*") if p.is_file()}
        | {p.relative_to(new_dir) for p in new_dir.rglob("*") if p.is_file()}
    )
    for rel in files:
        old_path, new_path = old_dir / rel, new_dir / rel
        old_lines = (
            old_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if old_path.exists()
            else []
        )
        new_lines = (
            new_path.read_text(encoding="utf-8").splitlines(keepends=True)
            if new_path.exists()
            else []
        )
        if old_lines == new_lines:
            continue
        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile=f"a/{rel.as_posix()}", tofile=f"b/{rel.as_posix()}"
        )
        chunks.append("".join(diff))
    return "".join(chunks)


def apply_patch(patch_text: str, target_dir: Path, *, timeout_s: float = 60) -> tuple[bool, str]:
    """Apply a unified diff to ``target_dir`` with ``patch -p1`` (scratch copies only).

    Patches that try to escape the directory (``..`` or absolute paths) or that
    contain no hunks are rejected before anything is applied.
    """
    if not patch_text.strip():
        return False, "empty patch"
    for line in patch_text.splitlines():
        if line.startswith(("+++ ", "--- ")):
            path = line[4:].split("\t")[0].strip()
            if path == "/dev/null":
                continue
            stripped = path.split("/", 1)[1] if "/" in path else path
            if path.startswith("/") or ".." in Path(stripped).parts:
                return False, f"patch touches a path outside the build context: {path}"
    if shutil.which("patch") is None:
        return False, "`patch` binary not available"
    result = procs.run(
        ["patch", "-p1", "--batch", "--forward", "--no-backup-if-mismatch", "-d", str(target_dir)],
        timeout_s=timeout_s,
        stdin_text=patch_text,
    )
    output = (result.stdout + result.stderr).strip()
    if result.timed_out:
        return False, "patch timed out"
    return result.ok, output


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-")[:64] or "experiment"


class ScriptedProposer(Proposer):
    """Deterministic queue of experiments loaded from a JSON file.

    Each entry: ``{"experiment": str, "hypothesis": str, "edits": [{"file": str,
    "find": str, "replace": str}], "notes": str}`` or a literal ``"patch"``.
    Edits are applied to a scratch copy of the current build context to render a
    real unified diff, so the stored patch is exactly what gets built.
    """

    name = "scripted"

    def __init__(self, queue: Sequence[Mapping[str, Any]], *, skip: int = 0) -> None:
        self._queue = list(queue)
        self._index = skip

    @classmethod
    def from_file(cls, path: Path, *, skip: int = 0) -> ScriptedProposer:
        """Load the queue from a JSON list (or ``{"experiments": [...]}``)."""
        data = json.loads(path.read_text(encoding="utf-8"))
        queue = data["experiments"] if isinstance(data, dict) else data
        return cls(queue, skip=skip)

    @property
    def remaining(self) -> int:
        """Experiments left in the queue."""
        return max(0, len(self._queue) - self._index)

    def propose(self, context: ProposerContext) -> Proposal | None:
        """Pop the next experiment and render its patch against ``context.context_dir``."""
        if self._index >= len(self._queue):
            return None
        entry = self._queue[self._index]
        self._index += 1
        experiment = _slug(str(entry["experiment"]))
        hypothesis = str(entry.get("hypothesis", ""))
        notes = str(entry.get("notes", ""))
        if "patch" in entry:
            return Proposal(experiment, hypothesis, str(entry["patch"]), notes)
        edits = entry.get("edits") or []
        if not edits:
            raise ProposerError(f"experiment {experiment} has neither patch nor edits")
        with tempfile.TemporaryDirectory(prefix="scripted-", dir=context.work_dir) as tmp:
            new_dir = Path(tmp) / "new"
            shutil.copytree(context.context_dir, new_dir)
            for edit in edits:
                target = new_dir / edit["file"]
                if ".." in Path(edit["file"]).parts or not target.is_file():
                    raise ProposerError(
                        f"experiment {experiment}: bad edit target {edit['file']!r}"
                    )
                text = target.read_text(encoding="utf-8")
                if edit.get("regex"):
                    pattern = re.compile(edit["find"])
                    found = pattern.search(text) is not None
                    patched = pattern.sub(edit["replace"].replace("\\", "\\\\"), text, count=1)
                else:
                    found = edit["find"] in text
                    patched = text.replace(edit["find"], edit["replace"], 1)
                if not found:
                    raise ProposerError(
                        f"experiment {experiment}: find-string not present in {edit['file']}: "
                        f"{edit['find']!r}"
                    )
                target.write_text(patched, encoding="utf-8")
            patch = unified_diff_for_dirs(context.context_dir, new_dir)
        if not patch.strip():
            raise ProposerError(f"experiment {experiment}: edits produced an empty patch")
        return Proposal(experiment, hypothesis, patch, notes)


@dataclass
class PiLaunchConfig:
    """How to launch the pinned Pi distribution."""

    pi_bin: Path
    agent_dir: Path
    api_key_env: str
    model: str | None = None
    provider: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 900.0
    usd_per_call_estimate: float = 0.0


def pi_version(pi_bin: Path, *, timeout_s: float = 60) -> str:
    """Return ``pi --version`` output (stripped)."""
    result = procs.run([str(pi_bin), "--version"], timeout_s=timeout_s, env=scrubbed_env({}))
    if not result.ok:
        raise ProposerError(
            f"pi --version failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def scrubbed_env(extra: Mapping[str, str], *, keep: Sequence[str] = ()) -> dict[str, str]:
    """Minimal child environment: PATH/HOME/LANG plus explicit extras; personal secrets dropped.

    Only variables named in ``keep`` survive the secret filter, so an API key
    reaches Pi only when the harness was configured to pass that exact name.
    """
    base = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TERM"}
    }
    for key in keep:
        if key in os.environ:
            base[key] = os.environ[key]
    for key, value in extra.items():
        base[key] = value
    return base


class PiProposer(Proposer):
    """Launch Pi 1.0.0 once per attempt and extract the single patch it writes."""

    name = "pi"

    def __init__(self, config: PiLaunchConfig, *, profile: Mapping[str, Any]) -> None:
        self.config = config
        self.profile = profile
        tools = tuple(profile.get("stock_tools", PI_STOCK_TOOLS))
        if tools != PI_STOCK_TOOLS:
            raise ProposerError(
                f"profile tools {tools} differ from the pinned stock tools {PI_STOCK_TOOLS}"
            )

    def verify_distribution(self) -> str:
        """Check ``pi --version`` matches the pinned version; return the version string."""
        version = pi_version(self.config.pi_bin)
        if version.split()[-1] != PI_VERSION:
            raise ProposerError(f"pi reports version {version!r}, expected {PI_VERSION}")
        return version

    def build_command(self, prompt_path: Path, session_dir: Path) -> list[str]:
        """The exact Pi invocation: print mode, JSON events, stock tools, isolation flags."""
        cmd = [
            str(self.config.pi_bin),
            "--print",
            "--mode",
            "json",
            "--tools",
            ",".join(PI_STOCK_TOOLS),
            *PI_ISOLATION_FLAGS,
            "--session-dir",
            str(session_dir),
        ]
        if self.config.provider:
            cmd += ["--provider", self.config.provider]
        if self.config.model:
            cmd += ["--model", self.config.model]
        cmd += ["@" + str(prompt_path)]
        return cmd

    def build_env(self) -> dict[str, str]:
        """Isolated env: task-scoped agent dir, telemetry off, key passed through by name only."""
        env = scrubbed_env(
            {
                "PI_CODING_AGENT_DIR": str(self.config.agent_dir),
                "PI_SKIP_VERSION_CHECK": "1",
                "PI_TELEMETRY": "0",
                **self.config.extra_env,
            },
            keep=(self.config.api_key_env,),
        )
        return env

    def api_key_present(self) -> bool:
        """Whether the configured key variable is set (value is never read into reports)."""
        return bool(os.environ.get(self.config.api_key_env))

    def render_prompt(self, context: ProposerContext, patch_out: Path, meta_out: Path) -> str:
        """Compose the agent instructions from program.md, the profile, and history."""
        history_lines = [
            f"- {h.get('experiment')}: outcome={h.get('outcome')} kept={h.get('kept')} "
            f"ttft_speedup={h.get('local_ttft_speedup', '')} "
            f"ftgr_speedup={h.get('local_ftgr_speedup', '')} "
            f"hypothesis={h.get('hypothesis', '')!r} notes={h.get('notes', '')!r}"
            for h in context.history
        ] or ["- (no attempts yet)"]
        return "\n".join(
            [
                context.program_md.strip(),
                "",
                "## Pi profile (organizer contract)",
                "```json",
                json.dumps(dict(context.profile), indent=2, sort_keys=True),
                "```",
                "",
                "## Engine under optimization",
                f"`{context.engine}`. Build context (the ONLY files you may change): "
                f"`{context.context_dir}`",
                "",
                "## Budget",
                context.budget_summary or "(not provided)",
                "",
                "## History of attempts so far (oldest first)",
                *history_lines,
                "",
                "## What you must output",
                "1. Pick exactly ONE experiment (one change), guided by the ranked hypotheses "
                "above and the history.",
                f"2. Edit files inside `{context.context_dir}` only. Do not run docker, "
                "do not start servers, do not touch anything else.",
                "3. Write a unified diff of your change (as produced by "
                "`diff -ruN original patched`, "
                f"applicable with `patch -p1`) to `{patch_out}`.",
                f"4. Write JSON to `{meta_out}` with keys `experiment` (short slug), "
                "`hypothesis` (one sentence: what metric improves and why), `notes`.",
                "5. Then stop. Do not print the patch to stdout.",
            ]
        )

    def propose(self, context: ProposerContext) -> Proposal | None:
        """Run Pi once and return its proposal; raise :class:`ProposerError` on misuse."""
        if not self.api_key_present():
            raise ProposerError(
                f"environment variable {self.config.api_key_env} is not set; PiProposer cannot run"
            )
        attempt_dir = Path(tempfile.mkdtemp(prefix="pi-attempt-", dir=context.work_dir))
        scratch = attempt_dir / "context"
        shutil.copytree(context.context_dir, scratch)
        patch_out = attempt_dir / "proposal.patch"
        meta_out = attempt_dir / "proposal.json"
        prompt_path = attempt_dir / "prompt.md"
        scratch_context = ProposerContext(
            context.program_md,
            context.profile,
            context.history,
            scratch,
            context.work_dir,
            context.engine,
            context.budget_summary,
        )
        prompt_path.write_text(
            self.render_prompt(scratch_context, patch_out, meta_out), encoding="utf-8"
        )
        session_dir = attempt_dir / "sessions"
        session_dir.mkdir()
        transcript = attempt_dir / "pi-events.jsonl"
        result = procs.run(
            self.build_command(prompt_path, session_dir),
            timeout_s=self.config.timeout_s,
            cwd=scratch,
            env=self.build_env(),
            log_path=transcript,
        )
        api_usd = self._cost_from_events(transcript)
        model_error = self._error_from_events(transcript)
        if result.timed_out:
            raise ProposerError(
                f"pi timed out after {self.config.timeout_s:.0f}s (transcript {transcript})",
                api_usd=api_usd,
            )
        if model_error is not None:
            raise ProposerError(
                f"pi model call failed: {model_error} (transcript {transcript})",
                api_usd=api_usd,
            )
        if not result.ok:
            raise ProposerError(
                f"pi exited {result.returncode} (transcript {transcript})", api_usd=api_usd
            )
        patch = (
            patch_out.read_text(encoding="utf-8")
            if patch_out.exists()
            else unified_diff_for_dirs(context.context_dir, scratch)
        )
        if not patch.strip():
            raise ProposerError(f"pi produced no patch (transcript {transcript})", api_usd=api_usd)
        meta: dict[str, Any] = {}
        if meta_out.exists():
            try:
                meta = json.loads(meta_out.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta = {}
        experiment = _slug(str(meta.get("experiment") or f"pi-{attempt_dir.name}"))
        return Proposal(
            experiment=experiment,
            hypothesis=str(meta.get("hypothesis", "")),
            patch=patch,
            notes=str(meta.get("notes", "")),
            api_usd=api_usd if api_usd is not None else self.config.usd_per_call_estimate,
            transcript_path=str(transcript),
        )

    @staticmethod
    def _cost_from_events(transcript: Path) -> float | None:
        """Sum ``message.usage.cost.total`` over ``message_end`` events; ``None`` if none.

        Pi's JSON mode (``dist/modes/json-event.js``) also attaches the running
        ``usage`` to every ``message_update`` delta, so only the terminal
        ``message_end`` event of each assistant message is counted.
        """
        total = 0.0
        seen = False
        for event in _iter_events(transcript):
            if event.get("type") != "message_end":
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            for cost in _find_costs(message.get("usage")):
                total += cost
                seen = True
        return total if seen else None

    @staticmethod
    def _error_from_events(transcript: Path) -> str | None:
        """Return the first ``errorMessage`` of an errored/aborted assistant message."""
        for event in _iter_events(transcript):
            if event.get("type") != "message_end":
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            if message.get("stopReason") in {"error", "aborted"}:
                return str(message.get("errorMessage") or message.get("stopReason"))
        return None


def _iter_events(transcript: Path) -> Iterator[dict[str, Any]]:
    """Yield parseable JSON-object lines of a Pi JSON transcript, skipping garbage."""
    if not transcript.exists():
        return
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _find_costs(node: Any) -> list[float]:
    found: list[float] = []
    if isinstance(node, dict):
        cost = node.get("cost")
        if isinstance(cost, dict) and isinstance(cost.get("total"), (int, float)):
            found.append(float(cost["total"]))
        for value in node.values():
            found.extend(_find_costs(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_find_costs(value))
    return found
