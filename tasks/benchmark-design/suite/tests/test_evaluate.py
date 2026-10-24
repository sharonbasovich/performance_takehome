"""End-to-end evaluator behaviour on synthetic evidence: status, startup, A/A, comparison."""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import evaluate as ev_mod

from tests.helpers import clean_cell, make_record, make_run, plan, write_events


def run_eval(the_plan, records, run=None, **run_kwargs):
    run = run or make_run(records, **run_kwargs)
    with tempfile.TemporaryDirectory() as tmp:
        write_events(Path(tmp), run, records)
        return ev_mod.evaluate(the_plan, Path(tmp), "native")


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = plan()
        self.n = self.plan["statistics"]["min_requests_per_cell"]

    def test_clean_run_is_valid_with_three_axes(self) -> None:
        records = clean_cell(self.plan, "chat_short_open", self.n)
        report, _, _ = run_eval(self.plan, records)
        self.assertEqual(report["status"], "valid", report)
        cell = report["cells"]["chat_short_open|rate=4rps"]
        self.assertIsNotNone(cell["ttft_s"]["p50"]["point"])
        self.assertLessEqual(cell["ttft_s"]["p50"]["low"], cell["ttft_s"]["p50"]["point"])
        self.assertEqual(cell["fluidity"]["strict"]["index_mean"]["point"], 1.0)
        self.assertIsNotNone(cell["decode"]["ftgr_tokens_per_s"])
        self.assertEqual(report["startup"]["startup_to_first_valid_generation_s"]["median"], 5.0)
        self.assertEqual(report["population"]["totals"]["completed"], self.n)

    def test_client_lag_invalidates_run(self) -> None:
        records = clean_cell(self.plan, "chat_short_open", self.n)
        report, _, _ = run_eval(self.plan, records, lag_max=0.5)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any("event-loop lag" in r for r in report["reasons"]))

    def test_aborted_run_and_schema_errors_invalid(self) -> None:
        records = clean_cell(self.plan, "chat_short_open", self.n)
        self.assertEqual(run_eval(self.plan, records, status="aborted")[0]["status"], "invalid")
        broken = copy.deepcopy(records)
        del broken[0]["events"]
        self.assertEqual(run_eval(self.plan, broken)[0]["status"], "invalid")

    def test_evidence_invalid_request_invalidates_run_but_server_faults_do_not(self) -> None:
        records = clean_cell(self.plan, "chat_short_open", self.n)
        records[0]["events"][2]["t"], records[0]["events"][3]["t"] = (
            records[0]["events"][3]["t"],
            records[0]["events"][2]["t"],
        )
        self.assertEqual(run_eval(self.plan, records)[0]["status"], "invalid")
        records = clean_cell(self.plan, "chat_short_open", self.n + 4)
        for i in range(4):
            records[i] = make_record(
                self.plan, request_id=records[i]["request_id"], index=i, send=100.0 + i, done=False
            )
        report, _, _ = run_eval(self.plan, records)
        self.assertEqual(report["status"], "valid", report["reasons"])
        totals = report["population"]["totals"]
        self.assertEqual((totals["unfinished"], totals["completed"]), (4, self.n))
        cell = report["cells"]["chat_short_open|rate=4rps"]
        self.assertLess(
            cell["fluidity"]["strict"]["index_mean"]["point"], 1.0
        )  # failures score FI = 0

    def test_too_few_requests_is_inconclusive_not_valid(self) -> None:
        report, _, _ = run_eval(self.plan, clean_cell(self.plan, "chat_short_open", self.n - 1))
        self.assertEqual(report["status"], "inconclusive")
        self.assertTrue(any("min_requests_per_cell" in r for r in report["inconclusive_reasons"]))

    def test_missing_evidence_is_never_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report, _, _ = ev_mod.evaluate(self.plan, Path(tmp), "native")
        self.assertEqual(report["status"], "invalid")
        report, _, _ = run_eval(self.plan, [])
        self.assertNotEqual(report["status"], "valid")

    def test_planned_vs_offered_accounting(self) -> None:
        records = clean_cell(self.plan, "chat_short_open", self.n)
        report, _, _ = run_eval(
            self.plan, records, planned={"chat_short_open|rate=4rps|rep0": self.n + 5}
        )
        unit = report["population"]["units"]["chat_short_open|rate=4rps|rep0"]
        self.assertEqual(
            (unit["planned"], unit["offered"], unit["not_offered"]), (self.n + 5, self.n, 5)
        )


class StartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = plan()
        self.records = clean_cell(
            self.plan, "chat_short_open", self.plan["statistics"]["min_requests_per_cell"]
        )

    def launch(self, **overrides):
        base = {
            "launch_index": 0,
            "launch_mono_s": 0.0,
            "cold": True,
            "launch_command_sha256": "0" * 64,
            "readiness_probes": [{"t": 2.0, "http_status": 200, "ok": True}],
            "generation_probe_request_ids": [],
            "readiness_at": 2.0,
            "first_valid_generation_at": 40.0,
            "first_valid_request_id": None,
            "status": "valid",
        }
        base.update(overrides)
        return base

    def test_readiness_does_not_stop_the_clock(self) -> None:
        report, _, _ = run_eval(self.plan, self.records, launch=self.launch())
        startup = report["startup"]["launches"][0]
        self.assertEqual(startup["first_ready_probe_s"], 2.0)
        self.assertEqual(startup["startup_to_first_valid_generation_s"], 40.0)
        self.assertEqual(startup["readiness_lead_s"], 38.0)
        self.assertEqual(report["startup"]["startup_to_first_valid_generation_s"]["median"], 40.0)

    def test_no_valid_generation_is_inconclusive(self) -> None:
        report, _, _ = run_eval(
            self.plan,
            self.records,
            launch=self.launch(first_valid_generation_at=None, status="timeout"),
        )
        self.assertEqual(report["status"], "inconclusive")
        self.assertTrue(any("startup" in r for r in report["inconclusive_reasons"]))

    def test_claimed_valid_probe_must_pass_gates(self) -> None:
        probe = make_record(
            self.plan,
            request_id="startup0/probe/1",
            phase="startup_probe",
            role="startup",
            done=False,
        )
        probe["unit_id"], probe["cell_id"], probe["arrival_type"], probe["load_label"] = (
            "startup",
            "startup",
            "probe",
            "probe",
        )
        launch = self.launch(
            generation_probe_request_ids=["startup0/probe/1"],
            first_valid_request_id="startup0/probe/1",
        )
        report, _, _ = run_eval(self.plan, [*self.records, probe], launch=launch)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any("fails the gates" in r for r in report["reasons"]))

    def test_attached_without_cold_launch_is_inconclusive(self) -> None:
        report, _, _ = run_eval(self.plan, self.records, launch=self.launch(cold=False))
        self.assertEqual(report["status"], "inconclusive")


class ControlAndComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = plan()
        self.n = max(self.plan["statistics"]["min_requests_per_cell"], 24)

    def _two_runs(self, shift_b: float = 0.0, n: int | None = None):
        n = n or self.n
        a = clean_cell(self.plan, "chat_short_open", n)
        b = clean_cell(self.plan, "chat_short_open", n, seed_shift=shift_b)
        with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
            write_events(Path(ta), make_run(a), a)
            write_events(Path(tb), make_run(b), b)
            base = ev_mod.evaluate(self.plan, Path(ta), "native")
            other = ev_mod.evaluate(self.plan, Path(tb), "native")
        return ev_mod.compare_runs(self.plan, base, other), base, other

    def test_aa_controls_never_yield_confident_regression(self) -> None:
        records = clean_cell(self.plan, "aa_control_a", self.n, role="aa_control") + clean_cell(
            self.plan, "aa_control_b", self.n, role="aa_control"
        )
        report, _, _ = run_eval(self.plan, records)
        self.assertIn(report["aa_control"]["decision"], ("no_difference", "inconclusive"))
        self.assertEqual(report["status"], "valid", report["reasons"])
        noisy = clean_cell(self.plan, "aa_control_a", self.n, role="aa_control")
        for i, r in enumerate(noisy):
            for e in r["events"]:
                e["t"] += 0.02 * ((i * 13) % 7) / 7
            r["timestamps_mono_s"]["end"] = r["events"][-1]["t"] + 0.001
            r["timestamps_mono_s"]["first_byte"] = r["events"][0]["t"]
        report, _, _ = run_eval(
            self.plan, noisy + clean_cell(self.plan, "aa_control_b", self.n, role="aa_control")
        )
        self.assertNotEqual(report["aa_control"]["decision"], "regression")

    def test_identical_runs_are_not_a_regression(self) -> None:
        decision, _, _ = self._two_runs()
        self.assertIn(decision["decision"], ("no_difference", "inconclusive"))
        self.assertEqual(decision["cells_compared"], 1)

    def test_clear_regression_detected(self) -> None:
        decision, _, _ = self._two_runs(shift_b=0.05)  # TTFT doubles: 50 ms -> 100 ms
        self.assertEqual(decision["decision"], "regression")
        metric = decision["per_cell"]["chat_short_open|rate=4rps"]["metrics"]["ttft_p50_s"]
        self.assertGreater(metric["difference"]["low"], 0)

    def test_underpowered_comparison_is_inconclusive(self) -> None:
        decision, _, _ = self._two_runs(
            shift_b=0.003, n=self.plan["statistics"]["min_requests_per_cell"]
        )
        self.assertIn(decision["decision"], ("inconclusive", "no_difference"))
        self.assertNotEqual(decision["decision"], "regression")

    def test_invalid_run_cannot_be_compared(self) -> None:
        a = clean_cell(self.plan, "chat_short_open", self.n)
        with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
            write_events(Path(ta), make_run(a), a)
            write_events(Path(tb), make_run(a, lag_max=1.0), a)
            base = ev_mod.evaluate(self.plan, Path(ta), "native")
            other = ev_mod.evaluate(self.plan, Path(tb), "native")
        self.assertEqual(ev_mod.compare_runs(self.plan, base, other)["decision"], "invalid")

    def test_cli_writes_report_and_summary(self) -> None:
        records = clean_cell(self.plan, "chat_short_open", self.n)
        with tempfile.TemporaryDirectory() as tmp:
            d = write_events(Path(tmp) / "ev", make_run(records), records)
            out, summary = Path(tmp) / "r.json", Path(tmp) / "s.md"
            with contextlib.redirect_stdout(io.StringIO()):
                code = ev_mod.main(
                    [
                        "--events",
                        str(d),
                        "--workload",
                        str(
                            Path(__file__).resolve().parent.parent
                            / "fixtures"
                            / "workload.mock.json"
                        ),
                        "--out",
                        str(out),
                        "--summary",
                        str(summary),
                        "--compare",
                        str(d),
                    ]
                )
            self.assertEqual(code, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["report_schema_version"], ev_mod.REPORT_SCHEMA_VERSION)
            self.assertIn(report["comparison"]["decision"], ("no_difference", "inconclusive"))
            self.assertIn("status **VALID**", summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
