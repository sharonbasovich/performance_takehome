"""The unattended optimization loop: propose -> build -> measure -> decide -> keep/revert.

Resilience properties (each is covered by a test under ``harness/tests``):

* every stage has a timeout; child processes run in their own process group
  and are killed on timeout; containers are stopped/removed on every path;
* every attempt (including build failures, startup timeouts, gate failures and
  interruptions) is appended to ``results.tsv`` and gets a report file;
* the last-good image is never deleted and is retagged on each keep;
* state is persisted to disk after every transition so a killed run resumes;
* SIGTERM/SIGINT finalize the current attempt as ``interrupted``, emit the
  last-good manifest, and exit;
* budget guards run before every attempt and reserve a final window.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import budget as budget_mod
from . import docker_runtime as docker
from . import measure as measure_mod
from . import procs
from . import results as results_mod
from .decision import Decision, decide
from .engines import CONTAINER_PORT, Engine
from .proposers import Proposal, Proposer, ProposerError, apply_patch, escaping_symlinks
from .state import HarnessState, ImageRef, InProgress, load_state, save_state, utc_ts


class Interrupted(Exception):
    """Raised inside the loop when a termination signal was received."""


@dataclass
class Timeouts:
    """Per-stage timeouts in seconds."""

    build_s: float = 1800.0
    startup_s: float = 300.0
    measure_s: float = 900.0
    propose_s: float = 900.0
    stop_grace_s: int = 10


@dataclass
class LoopConfig:
    """Everything the loop needs; built by ``run.py`` from CLI flags."""

    repo_root: Path
    state_dir: Path
    results_path: Path
    reports_dir: Path
    patches_dir: Path
    benchmark_path: Path
    program_path: Path
    out_manifest: Path
    source_commit: str
    budget: budget_mod.BudgetConfig
    timeouts: Timeouts = field(default_factory=Timeouts)
    max_attempts: int | None = None
    network_name: str = "abstract-harness-net"
    container_prefix: str = "abstract-harness"
    image_prefix: str = "abstract-harness"
    min_effect: float = 0.03
    no_cache: bool = False
    startup_regression_limit: float = 1.5
    harness_tree_sha256: str = ""
    min_samples: int = 3
    estimated_attempt_s: float = 600.0
    keep_candidate_images: bool = False
    repo_relative_base: Path | None = None

    def rel(self, path: Path) -> str:
        """Repository-root-relative POSIX path for TSV/report references."""
        base = self.repo_relative_base or self.repo_root
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


class Harness:
    """Owns one engine, one proposer, one state file, and drives the loop."""

    def __init__(
        self,
        config: LoopConfig,
        engine: Engine,
        proposer: Proposer,
        *,
        log: Callable[[str], None] = print,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.engine = engine
        self.proposer = proposer
        self.log = log
        self.clock = clock
        self.state_path = config.state_dir / "state.json"
        self._lock: Any = None
        self._results_lock: Any = None
        # Locks first: nothing below may touch state.json or results.tsv until we own both.
        self._lock = procs.acquire_lock(config.state_dir / "harness.lock")
        self._results_lock = procs.acquire_lock(
            config.results_path.with_suffix(config.results_path.suffix + ".lock")
        )
        self._attempt_deadline: float | None = None
        self.benchmark = measure_mod.load_benchmark(config.benchmark_path)
        self.state = load_state(self.state_path, on_warning=log) or HarnessState(
            engine=engine.name,
            source_commit=config.source_commit,
            lease_start_ts=config.budget.lease_start_ts,
        )
        self._stop_requested = False
        self._stop_signal = ""
        self._active_container: str | None = None
        for d in (config.state_dir, config.reports_dir, config.patches_dir):
            d.mkdir(parents=True, exist_ok=True)
        results_mod.repair_torn_tail(config.results_path, log=log)
        results_mod.ensure_header(config.results_path)
        if self.state.harness_tree_sha256 and config.harness_tree_sha256:
            if self.state.harness_tree_sha256 != config.harness_tree_sha256:
                log(
                    "[harness] WARNING: harness code changed since this state directory was "
                    f"created ({self.state.harness_tree_sha256[:12]} -> "
                    f"{config.harness_tree_sha256[:12]}); rows will carry the new source_commit"
                )
        self.state.harness_tree_sha256 = (
            config.harness_tree_sha256 or self.state.harness_tree_sha256
        )
        if self.state.source_commit != config.source_commit:
            self.state.source_commit = config.source_commit

    def _release_locks(self) -> None:
        results_lock = self.config.results_path.with_suffix(
            self.config.results_path.suffix + ".lock"
        )
        for name in ("_results_lock", "_lock"):
            fh = getattr(self, name, None)
            if fh is not None:
                fh.close()
                setattr(self, name, None)
                if name == "_results_lock":
                    results_lock.unlink(missing_ok=True)

    # ------------------------------------------------------------------ signals
    def install_signal_handlers(self) -> None:
        """Handle SIGTERM/SIGINT by requesting a graceful stop at the next checkpoint."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._on_signal)

    def _on_signal(self, signum: int, _frame: Any) -> None:
        name = signal.Signals(signum).name
        if self._stop_requested:
            # Second signal: abort whatever is running (even finalize); a third one is fatal.
            self.log(f"[harness] received {name} again; aborting")
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, signal.SIG_DFL)
            raise Interrupted(name)
        self._stop_requested = True
        self._stop_signal = name
        self.log(f"[harness] received {name}; stopping at the next checkpoint and finalizing")

    def _should_abort(self) -> bool:
        return self._stop_requested

    def _checkpoint(self) -> None:
        if self._stop_requested:
            raise Interrupted(self._stop_signal or "signal")

    # ------------------------------------------------------------------ helpers
    def _save(self) -> None:
        ip = self.state.in_progress
        if ip is not None and not ip.attempt_index:
            ip.attempt_index = self.state.attempt_index
        save_state(self.state_path, self.state)

    def _stage_timeout(self, configured_s: float) -> float:
        if self._attempt_deadline is None:
            return configured_s
        return budget_mod.stage_timeout(configured_s, self._attempt_deadline)

    def _gpu_hours(self) -> float:
        return budget_mod.gpu_hours_used(self.config.budget, self.now())

    def now(self) -> float:
        """Wall clock for budgets, clamped so it never moves backwards across checkpoints."""
        ts, went_back = budget_mod.monotone_now(self.clock(), self.state.last_clock_ts)
        if went_back:
            self.log("[harness] wall clock went backwards; budgets use the last seen timestamp")
        self.state.last_clock_ts = ts
        return ts

    def _report_path(self, experiment: str) -> Path:
        return self.config.reports_dir / f"{self.state.attempt_index:03d}-{experiment}.json"

    def _write_report(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )

    def _append_row(self, **fields: str) -> None:
        """Append one row unless a row for this experiment id already exists (idempotent)."""
        if results_mod.has_experiment(self.config.results_path, fields["experiment"]):
            self.log(
                f"[harness] results.tsv already has a row for {fields['experiment']}; not appending"
            )
            return
        gpu_hours = "" if self.config.budget.gpus_allocated == 0 else f"{self._gpu_hours():.4f}"
        row = results_mod.make_row(
            ts=utc_ts(self.clock()),
            source_commit=self.state.source_commit,
            api_usd_cumulative=f"{self.state.api_usd_cumulative:.4f}",
            gpu_hours_cumulative=gpu_hours,
            **fields,
        )
        results_mod.append_row(self.config.results_path, row)
        self.state.history.append({k: getattr(row, k) for k in results_mod.COLUMNS})
        if self.state.in_progress is not None:
            self.state.in_progress.row_written = True

    def _is_alive(self, container: str) -> Callable[[], bool]:
        return lambda: docker.container_running(container)

    def _stop_active_container(self) -> None:
        if self._active_container:
            docker.stop_container(self._active_container, grace_s=self.config.timeouts.stop_grace_s)
            self._active_container = None

    def cleanup(self) -> None:
        """Kill any container this harness instance may have left behind."""
        self._stop_active_container()
        docker.kill_containers_with_prefix(self.config.container_prefix + "-")

    # ------------------------------------------------------------------ stages
    @property
    def last_good_context(self) -> Path:
        """Build context that produced the last-good image (kept patches accumulate here)."""
        return self.config.state_dir / "last-good-context"

    def _promote_context(self, source: Path) -> None:
        target = self.last_good_context
        tmp = target.with_name(target.name + ".tmp")
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(source, tmp)
        if target.exists():
            shutil.rmtree(target)
        os.replace(tmp, target)

    def build(self, context_dir: Path, tag: str, log_path: Path) -> docker.BuildResult:
        """Build a fresh image from ``context_dir`` (digest resolved from the result)."""
        return docker.build_image(
            context_dir,
            tag,
            log_path=log_path,
            timeout_s=self._stage_timeout(self.config.timeouts.build_s),
            platform=self.engine.spec.platform,
            dockerfile=context_dir / self.engine.spec.dockerfile.name,
            no_cache=self.config.no_cache,
            should_abort=self._should_abort,
        )

    def measure_image(
        self, image: str, *, golden: dict[str, str] | None, label: str
    ) -> tuple[measure_mod.Measurement, dict[str, Any]]:
        """Start a container from ``image``, measure startup + benchmark, always stop it."""
        container = f"{self.config.container_prefix}-{label}-{int(self.clock()) % 100000}"
        quiet = procs.wait_for_quiet_host(should_abort=self._should_abort)
        if not quiet["quiet"]:
            self.log(f"[harness] host did not go quiet before {label} (idle={quiet['idle']})")
        docker.ensure_internal_network(self.config.network_name)
        runtime_args = self.engine.full_runtime_args(docker.image_cmd(image))
        command = self.engine.run_command(
            image, container, self.config.network_name, runtime_args=runtime_args
        )
        started = time.monotonic()
        self._active_container = container
        if self.state.in_progress:
            self.state.in_progress.container = container
            self.state.in_progress.stage = "starting"
            self._save()
        info: dict[str, Any] = {
            "container": container,
            "command": command,
            "runtime_args": runtime_args,
        }
        try:
            docker.run_detached(command)
            ip = None
            deadline = time.monotonic() + 30
            while ip is None and time.monotonic() < deadline:
                self._checkpoint()
                ip = docker.container_ip(container, self.config.network_name)
                if ip is None:
                    if not docker.container_running(container):
                        raise measure_mod.MeasurementError(
                            "container exited immediately: "
                            + docker.container_logs(container, 40)[-1500:]
                        )
                    time.sleep(0.2)
            if ip is None:
                raise measure_mod.MeasurementError(
                    "container never obtained an address on the internal network"
                )
            base_url = f"http://{ip}:{CONTAINER_PORT}"
            info["base_url"] = base_url
            info["host_quiet_before_start"] = quiet
            startup_s, model_id = measure_mod.wait_for_first_valid_generation(
                base_url,
                started,
                self.benchmark,
                timeout_s=self._stage_timeout(self.config.timeouts.startup_s),
                is_alive=self._is_alive(container),
            )
            self._checkpoint()
            if self.state.in_progress:
                self.state.in_progress.stage = "measuring"
                self._save()
            measurement = measure_mod.run_benchmark(
                base_url,
                model_id,
                self.benchmark,
                golden=golden,
                startup_s=startup_s,
                is_alive=self._is_alive(container),
            )
            if time.monotonic() - started > self._stage_timeout(
                self.config.timeouts.startup_s + self.config.timeouts.measure_s
            ):
                raise measure_mod.MeasurementError("measurement exceeded its time budget")
            return measurement, info
        finally:
            info["container_log_tail"] = docker.container_logs(container, 60)[-4000:]
            self._stop_active_container()

    # ------------------------------------------------------------------ baseline
    def establish_baseline(self) -> None:
        """Build + measure the unpatched build context; it becomes last-good and the golden set."""
        if self.state.last_good is not None:
            self.log(
                f"[harness] baseline already established: {self.state.last_good.tag} "
                f"{self.state.last_good.digest}"
            )
            return
        experiment = "baseline"
        tag = f"{self.config.image_prefix}-{self.engine.name}:baseline"
        report_path = self._report_path(experiment)
        self.state.in_progress = InProgress(
            experiment,
            "unpatched build context",
            self.clock(),
            "",
            stage="building",
            image_tag=tag,
            attempt_index=self.state.attempt_index,
            report_path=self.config.rel(report_path),
        )
        self._save()
        log_path = self.config.state_dir / "logs" / "000-baseline.build.log"
        report: dict[str, Any] = {
            "experiment": experiment,
            "engine": self.engine.name,
            "kind": "baseline",
            "started_ts": utc_ts(self.clock()),
        }
        try:
            self._checkpoint()
            build = self.build(self.engine.spec.build_context, tag, log_path)
            report["build"] = _build_summary(build, self.config)
            if not build.ok or not build.digest:
                raise RuntimeError(f"baseline build failed: {build.error}")
            self._checkpoint()
            measurement, info = self.measure_image(tag, golden=None, label="baseline")
            report["measurement"] = measurement.to_json()
            report["container"] = info
            if not measurement.gates_passed:
                raise RuntimeError(
                    "baseline failed its own correctness gates: "
                    + "; ".join(f"{g.name}: {g.detail}" for g in measurement.gates if not g.passed)
                )
            self.state.baseline_samples = measurement.samples()
            self.state.golden = measure_mod.golden_from(measurement)
            self.state.last_good = ImageRef(
                tag, build.digest, build.image_id, experiment, self.config.rel(report_path)
            )
            docker.retag(tag, f"{self.config.image_prefix}-{self.engine.name}:last-good")
            self._promote_context(self.engine.spec.build_context)
            report["decision"] = {"outcome": "baseline", "kept": True}
            self._write_report(report_path, report)
            self._append_row(
                experiment=experiment,
                image_digest=build.digest,
                kept="1",
                outcome="baseline",
                local_startup_s=results_mod.format_metric(measurement.startup_s, 3),
                hypothesis="unpatched build context establishes last-good image, "
                "golden outputs, and noise floor",
                notes=f"ttft_median_s={_median(measurement.ttft_samples)} "
                f"ftgr_median_tok_s={_median(measurement.ftgr_samples)} "
                f"reps={measurement.repetitions}",
                development_report=self.config.rel(report_path),
                patch_path="",
            )
            self.state.in_progress = None
            self.state.attempt_index += 1
            self._save()
        except Interrupted:
            report["interrupted"] = True
            self._write_report(report_path, report)
            self._append_row(
                experiment=experiment,
                image_digest="",
                kept="0",
                outcome="interrupted",
                hypothesis="baseline",
                notes=f"interrupted by {self._stop_signal} during baseline",
                development_report=self.config.rel(report_path),
                patch_path="",
            )
            self.state.in_progress = None
            self._save()
            raise
        except Exception as exc:  # noqa: BLE001 - every failure must be logged, not crash the loop
            report["error"] = f"{type(exc).__name__}: {exc}"
            report["traceback"] = traceback.format_exc()
            self._write_report(report_path, report)
            self._append_row(
                experiment=experiment,
                image_digest="",
                kept="0",
                outcome="error",
                hypothesis="baseline",
                notes=report["error"][:500],
                development_report=self.config.rel(report_path),
                patch_path="",
            )
            self.state.in_progress = None
            self.state.finished = True
            self.state.finish_reason = "baseline failed"
            self._save()
            raise

    # ------------------------------------------------------------------ attempt
    def attempt(self, proposal: Proposal) -> str:
        """Run one experiment end to end; returns the outcome string written to results.tsv."""
        assert self.state.last_good is not None
        idx = self.state.attempt_index
        experiment = f"{idx:03d}-{proposal.experiment}"
        patch_path = self.config.patches_dir / f"{experiment}.patch"
        patch_path.write_text(proposal.patch, encoding="utf-8")
        report_path = self._report_path(proposal.experiment)
        tag = f"{self.config.image_prefix}-{self.engine.name}:{experiment}"
        self.state.api_usd_cumulative += max(0.0, proposal.api_usd)
        self.state.in_progress = InProgress(
            experiment,
            proposal.hypothesis,
            self.clock(),
            self.config.rel(patch_path),
            stage="building",
            image_tag=tag,
            attempt_index=self.state.attempt_index,
            report_path=self.config.rel(report_path),
        )
        self._save()
        report: dict[str, Any] = {
            "experiment": experiment,
            "engine": self.engine.name,
            "kind": "attempt",
            "started_ts": utc_ts(self.clock()),
            "hypothesis": proposal.hypothesis,
            "proposer": self.proposer.name,
            "proposal_notes": proposal.notes,
            "patch_path": self.config.rel(patch_path),
            "transcript": proposal.transcript_path,
            "last_good_before": asdict(self.state.last_good),
        }
        scratch = self.config.state_dir / "scratch" / experiment
        attempt_start = time.monotonic()
        outcome = "error"
        digest = ""
        kept = "0"
        notes = ""
        ttft = ftgr = ""
        startup = ""
        try:
            self._checkpoint()
            if scratch.exists():
                shutil.rmtree(scratch)
            source_context = (
                self.last_good_context
                if self.last_good_context.exists()
                else self.engine.spec.build_context
            )
            bad_links = escaping_symlinks(source_context)
            if bad_links:
                raise RuntimeError(f"build context has symlinks escaping it: {bad_links}")
            shutil.copytree(source_context, scratch, symlinks=True)
            ok, output = apply_patch(proposal.patch, scratch)
            report["patch_apply"] = {"ok": ok, "output": output[-2000:]}
            if not ok:
                raise RuntimeError(f"patch did not apply: {output[-300:]}")
            self._checkpoint()
            build = self.build(
                scratch, tag, self.config.state_dir / "logs" / f"{experiment}.build.log"
            )
            report["build"] = _build_summary(build, self.config)
            if not build.ok or not build.digest:
                raise RuntimeError(f"build failed: {build.error}")
            digest = build.digest
            self._checkpoint()
            # A/B: re-measure the last-good image in the same attempt so slow drift in
            # host load affects both arms; the stored baseline is only a fallback.
            assert self.state.last_good is not None
            baseline_samples = self.state.baseline_samples
            if docker.image_exists(self.state.last_good.tag):
                base_measurement, base_info = self.measure_image(
                    self.state.last_good.tag, golden=self.state.golden, label=f"{idx:03d}-ab"
                )
                report["baseline_measurement"] = base_measurement.to_json()
                report["baseline_container"] = base_info
                if base_measurement.gates_passed:
                    baseline_samples = base_measurement.samples()
                else:
                    report["baseline_remeasure_note"] = (
                        "last-good re-measure failed gates; using stored samples"
                    )
            self._checkpoint()
            measurement, info = self.measure_image(
                tag, golden=self.state.golden, label=f"{idx:03d}"
            )
            report["measurement"] = measurement.to_json()
            report["container"] = info
            decision = decide(
                baseline_samples,
                measurement.samples(),
                gates_passed=measurement.gates_passed,
                gate_summary="; ".join(
                    f"{g.name}: {g.detail}" for g in measurement.gates if not g.passed
                ),
                min_effect=self.config.min_effect,
                min_samples=self.config.min_samples,
                startup_regression_limit=self.config.startup_regression_limit,
            )
            report["decision"] = _decision_summary(decision)
            outcome = decision.outcome
            notes = decision.reason
            ttft = results_mod.format_metric(_speedup(decision, "ttft_s"))
            ftgr = results_mod.format_metric(_speedup(decision, "ftgr_tok_s"))
            startup = results_mod.format_metric(measurement.startup_s, 3)
            if decision.kept:
                kept = "1"
                self.state.last_good = ImageRef(
                    tag,
                    build.digest,
                    build.image_id,
                    experiment,
                    self.config.rel(report_path),
                    self.config.rel(patch_path),
                )
                self.state.baseline_samples = measurement.samples()
                docker.retag(tag, f"{self.config.image_prefix}-{self.engine.name}:last-good")
                self._promote_context(scratch)
                self.log(f"[harness] KEPT {experiment} -> {build.digest}")
            else:
                self.log(f"[harness] reverted {experiment}: {outcome} ({notes})")
                if not self.config.keep_candidate_images:
                    docker.remove_image(tag)
        except Interrupted:
            outcome = "interrupted"
            stage = self.state.in_progress.stage if self.state.in_progress else "?"
            notes = f"interrupted by {self._stop_signal} during stage {stage}"
            report["interrupted"] = notes
        except (
            RuntimeError,
            measure_mod.MeasurementError,
            docker.DockerError,
            OSError,
            ValueError,
        ) as exc:
            if self._stop_requested:
                outcome = "interrupted"
                notes = f"interrupted by {self._stop_signal} ({type(exc).__name__}: {exc})"
                report["interrupted"] = notes
            else:
                outcome = "error"
                notes = f"{type(exc).__name__}: {exc}"
                report["error"] = notes
                report["traceback"] = traceback.format_exc()
            if not self.config.keep_candidate_images and docker.image_exists(tag):
                docker.remove_image(tag)
        finally:
            self._stop_active_container()
            shutil.rmtree(scratch, ignore_errors=True)
            report["finished_ts"] = utc_ts(self.clock())
            report["outcome"] = outcome
            report["kept"] = kept == "1"
            report["last_good_after"] = asdict(self.state.last_good)
            self._write_report(report_path, report)
            self._append_row(
                experiment=experiment,
                image_digest=digest,
                kept=kept,
                outcome=outcome,
                local_ttft_speedup=ttft,
                local_ftgr_speedup=ftgr,
                local_startup_s=startup,
                hypothesis=proposal.hypothesis,
                notes=notes[:900],
                development_report=self.config.rel(report_path),
                patch_path=self.config.rel(patch_path),
            )
            self.state.attempt_durations_s.append(round(time.monotonic() - attempt_start, 3))
            self.state.in_progress = None
            self.state.attempt_index += 1
            self._save()
        return outcome

    # ------------------------------------------------------------------ resume
    def recover_from_previous_run(self) -> None:
        """If a previous process died mid-attempt, log that attempt as ``interrupted``."""
        self._reconcile_attempt_index()
        ip = self.state.in_progress
        if ip is None:
            return
        if results_mod.has_experiment(self.config.results_path, ip.experiment):
            self.log(
                f"[harness] results.tsv already records {ip.experiment}; the previous process "
                "died after writing the row - clearing the in-progress marker only"
            )
            docker.kill_containers_with_prefix(self.config.container_prefix + "-")
            self.state.in_progress = None
            self.state.attempt_index = max(self.state.attempt_index, ip.attempt_index + 1)
            self._save()
            return
        self.log(
            f"[harness] previous run died during {ip.experiment} ({ip.stage}); "
            "logging as interrupted"
        )
        docker.kill_containers_with_prefix(self.config.container_prefix + "-")
        report_path = (
            self.config.repo_root / ip.report_path
            if ip.report_path
            else self._report_path(
                ip.experiment.split("-", 1)[-1] if ip.experiment != "baseline" else "baseline"
            )
        )
        if report_path.exists():
            # Never overwrite a report the previous process finished writing.
            report_path = report_path.with_suffix(".recovered.json")
        report = {
            "experiment": ip.experiment,
            "kind": "recovered",
            "stage": ip.stage,
            "hypothesis": ip.hypothesis,
            "started_ts": utc_ts(ip.started_ts),
            "note": "process was not running when the harness restarted; "
            "attempt logged as interrupted",
        }
        self._write_report(report_path, report)
        self._append_row(
            experiment=ip.experiment,
            image_digest="",
            kept="0",
            outcome="interrupted",
            hypothesis=ip.hypothesis,
            notes=f"recovered on restart: previous process died during stage {ip.stage}",
            development_report=self.config.rel(report_path),
            patch_path=ip.patch_path,
        )
        if ip.image_tag and ip.image_tag != (
            self.state.last_good.tag if self.state.last_good else ""
        ):
            docker.remove_image(ip.image_tag)
        self.state.in_progress = None
        self.state.attempt_index = max(self.state.attempt_index, ip.attempt_index) + 1
        self._save()

    def _reconcile_attempt_index(self) -> None:
        """Never reuse an attempt number results.tsv already contains (e.g. after a .bak rewind)."""
        try:
            rows = results_mod.read_rows(self.config.results_path)
        except results_mod.ResultsError as exc:
            raise RuntimeError(f"results file is not usable for resume: {exc}") from exc
        highest = 0
        for row in rows:
            prefix = row.experiment.split("-", 1)[0]
            if prefix.isdigit():
                highest = max(highest, int(prefix))
        if rows and self.state.attempt_index <= highest:
            self.log(
                f"[harness] attempt index {self.state.attempt_index} is behind results.tsv "
                f"({highest}); advancing"
            )
            self.state.attempt_index = highest + 1

    # ------------------------------------------------------------------ main loop
    def run(self) -> int:
        """Drive the loop until the proposer, budget, attempt cap, or a signal stops it.

        Returns a process exit code: 0 normal, 3 interrupted, 2 baseline failure,
        4 when another instance holds the state-directory lock.
        """
        self.install_signal_handlers()
        try:
            self.recover_from_previous_run()
            if self.state.finished:
                self.log(
                    f"[harness] state marked finished ({self.state.finish_reason}); "
                    "writing manifest only"
                )
                self.finalize("already finished")
                return 0
            self.establish_baseline()
            attempts = 0
            while True:
                self._checkpoint()
                if self.config.max_attempts is not None and attempts >= self.config.max_attempts:
                    self.finalize("attempt cap reached")
                    return 0
                t = self.config.timeouts
                worst_case_s = budget_mod.worst_case_attempt_s(
                    propose_s=t.propose_s,
                    build_s=t.build_s,
                    startup_s=t.startup_s,
                    measure_s=t.measure_s,
                    stop_grace_s=t.stop_grace_s,
                )
                estimate_s = budget_mod.attempt_estimate_s(
                    self.config.estimated_attempt_s, self.state.attempt_durations_s
                )
                verdict = budget_mod.check_before_attempt(
                    self.config.budget,
                    api_usd_cumulative=self.state.api_usd_cumulative,
                    now_ts=self.now(),
                    estimated_attempt_s=estimate_s,
                    estimated_attempt_usd=self.proposer.estimated_usd_per_call(),
                )
                # Hard bound: no stage may run past the lease's usable window, even if the
                # configured timeouts (worst case = worst_case_s) would allow it.
                self._attempt_deadline = time.monotonic() + max(
                    0.0, min(worst_case_s, verdict.usable_seconds_remaining)
                )
                self.log(
                    f"[harness] budget check: {verdict.reason} "
                    f"(api_usd_remaining={verdict.api_usd_remaining:.2f}, "
                    f"gpu_h_used={verdict.gpu_hours_used:.3f}, "
                    f"usable_s={verdict.usable_seconds_remaining:.0f})"
                )
                if not verdict.ok:
                    self.finalize(f"budget guard: {verdict.reason}")
                    return 0
                try:
                    proposal = self.proposer.propose(self._proposer_context(verdict))
                except ProposerError as exc:
                    self.log(f"[harness] proposer error: {exc}")
                    self.state.api_usd_cumulative += exc.api_usd or 0.0
                    self._append_row(
                        experiment=f"{self.state.attempt_index:03d}-proposer",
                        image_digest="",
                        kept="0",
                        outcome="error",
                        hypothesis="",
                        notes=f"proposer error: {exc}"[:900],
                        development_report="",
                        patch_path="",
                    )
                    self.state.attempt_index += 1
                    self._save()
                    attempts += 1
                    continue
                if proposal is None:
                    self.finalize("proposer exhausted")
                    return 0
                self.attempt(proposal)
                attempts += 1
        except Interrupted:
            self.finalize(f"interrupted by {self._stop_signal}")
            return 3
        except Exception as exc:  # noqa: BLE001 - last line of defence: always finalize
            self.log(f"[harness] fatal {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            self.finalize(f"fatal: {type(exc).__name__}: {exc}")
            return 2
        finally:
            self._release_locks()
            self.cleanup()

    def _proposer_context(self, verdict: budget_mod.BudgetVerdict) -> Any:
        from .proposers import ProposerContext

        profile = json.loads(
            (self.config.repo_root / "agent-harness" / "profiles.json").read_text(encoding="utf-8")
        )["profiles"]["harness-design"]
        summary = (
            f"api_usd_remaining={verdict.api_usd_remaining:.2f}; "
            f"gpu_hours_used={verdict.gpu_hours_used:.3f}; "
            f"usable_seconds_remaining={verdict.usable_seconds_remaining:.0f}"
        )
        work = self.config.state_dir / "proposer"
        work.mkdir(parents=True, exist_ok=True)
        return ProposerContext(
            program_md=self.config.program_path.read_text(encoding="utf-8"),
            profile=profile,
            history=list(self.state.history),
            context_dir=(
                self.last_good_context
                if self.last_good_context.exists()
                else self.engine.spec.build_context
            ),
            work_dir=work,
            engine=self.engine.name,
            budget_summary=summary,
        )

    # ------------------------------------------------------------------ finalize
    def finalize(self, reason: str) -> dict[str, Any]:
        """Write the last-good manifest + integrity report and mark the state finished."""
        from .manifest import write_manifest

        self.state.finish_reason = reason
        self._save()
        manifest = write_manifest(self)
        self.log(f"[harness] finalized ({reason}); last-good={manifest.get('image')}")
        return manifest


def _median(values: list[float]) -> str:
    if not values:
        return ""
    ordered = sorted(values)
    mid = len(ordered) // 2
    value = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return f"{value:.4f}"


def _speedup(decision: Decision, metric: str) -> float | None:
    comp = decision.comparison(metric)
    return comp.speedup if comp else None


def _build_summary(build: docker.BuildResult, config: LoopConfig) -> dict[str, Any]:
    return {
        "ok": build.ok,
        "timed_out": build.timed_out,
        "duration_s": round(build.duration_s, 2),
        "no_cache": config.no_cache,
        "tag": build.tag,
        "image_id": build.image_id,
        "digest": build.digest,
        "log": config.rel(build.log_path),
        "error": build.error,
    }


def _decision_summary(decision: Decision) -> dict[str, Any]:
    return {
        "outcome": decision.outcome,
        "kept": decision.kept,
        "reason": decision.reason,
        "comparisons": [asdict(c) for c in decision.comparisons],
    }


__all__ = ["Harness", "LoopConfig", "Timeouts", "Interrupted", "subprocess"]
