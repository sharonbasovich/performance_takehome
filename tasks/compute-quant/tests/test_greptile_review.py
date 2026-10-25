"""End-to-end regressions for the first Greptile review of the synthetic pipeline."""

import json
import unittest

from research.pipeline import load_config, render_json
from research.report import render_report

from .support import CaseBuilder, quote_row, run_cli, run_demo


class GreptileReviewTests(unittest.TestCase):
    def test_missing_usage_writes_finite_outputs_and_report(self):
        builder = CaseBuilder(self)
        builder.case["reservation"].pop("expected_buyer_used_fraction")
        result = builder.run()
        info = json.loads(render_json(result))["valuation"]["usage_is_informational_only"]
        self.assertIsNone(info["expected_used_fraction"])
        self.assertIsNone(info["effective_usd_per_used_gpu_hour"])
        self.assertEqual(info["fees_owed_usd"], 9720.0)
        self.assertIn("not supplied", render_report(result))
        proc = run_cli(
            "--case",
            str(builder.write()),
            "--out",
            str(builder.dir / "out"),
            "--report",
            str(builder.dir / "REPORT.md"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_zero_usage_preserves_zero_and_full_fees(self):
        builder = CaseBuilder(self)
        builder.case["reservation"]["expected_buyer_used_fraction"] = 0
        result = builder.run()
        info = json.loads(render_json(result))["valuation"]["usage_is_informational_only"]
        self.assertEqual(info["expected_used_fraction"], 0)
        self.assertEqual(info["WRONG_fees_scaled_by_usage_usd"], 0)
        self.assertIsNone(info["effective_usd_per_used_gpu_hour"])
        self.assertEqual(result["valuation"]["buyer_mark"], run_demo()["valuation"]["buyer_mark"])
        self.assertIn("zero expected use", render_report(result))

    def test_multimonth_node_month_is_excluded_not_diluted(self):
        result = CaseBuilder(self).set("q07", delivery_end="2027-01-01T00:00:00Z").run()
        row = quote_row(result, "q07")
        self.assertIsNone(row["usd_per_gpu_hour"])
        self.assertIn("one UTC calendar month", row["excluded_reason"])
        self.assertFalse(row["curve_eligible"])

    def test_advance_paid_strip_is_excluded_without_payment_schedule(self):
        builder = CaseBuilder(self).copy_quote(
            "q04",
            "advance-strip",
            delivery_end="2027-02-01T00:00:00Z",
            payment="advance",
            price="0.01",
        )
        result = builder.run()
        row = quote_row(result, "advance-strip")
        self.assertIsNone(row["usd_per_gpu_hour"])
        self.assertIn("monthly payment schedule", row["excluded_reason"])
        self.assertEqual(result["valuation"]["buyer_mark"], run_demo()["valuation"]["buyer_mark"])

    def test_arrears_hourly_strip_stays_supported(self):
        result = (
            CaseBuilder(self)
            .copy_quote(
                "q04",
                "arrears-strip",
                delivery_end="2027-02-01T00:00:00Z",
                payment="arrears",
                price="4.70",
            )
            .run()
        )
        row = quote_row(result, "arrears-strip")
        self.assertEqual(row["usd_per_gpu_hour"], 4.7)
        self.assertTrue(row["curve_eligible"])

    def test_quantity_calibration_requires_explicit_cancel_anytime_rights(self):
        for cancellation in ("none", "unsupported"):
            with self.subTest(cancellation=cancellation):
                result = CaseBuilder(self).set("q02", cancellation=cancellation).run()
                self.assertIsNone(result["quantity_adjustment"]["factor"])
                self.assertEqual(quote_row(result, "q02")["contract_class"], "unclassified_rights")
                self.assertFalse(quote_row(result, "q07")["curve_eligible"])

    def test_memo_compares_current_contract_price_to_current_flexible_ask(self):
        builder = CaseBuilder(self)
        builder.case["reservation"]["fixed_usd_per_gpu_hour"] = 8
        report = render_report(builder.run())
        self.assertNotIn("the reservation is cheaper than", report)
        self.assertIn("$8.0000", report)
        self.assertIn("above the comparable", report)

    def test_memo_does_not_claim_missing_bid_after_one_is_added(self):
        result = CaseBuilder(self).copy_quote("q04", "nov-bid", side="bid", price="4.5").run()
        report = render_report(result)
        self.assertNotIn("No bid exists for Nov-2026", report)
        self.assertNotIn("Nov-2026 ask is therefore an interval edge", report)
        self.assertIn("2026-11", report)

    def test_flexible_price_summary_uses_evidence_beyond_quote_example_cap(self):
        builder = CaseBuilder(self)
        builder.quotes = builder.quotes[1:] + builder.quotes[:1]
        builder.case["reservation"]["fixed_usd_per_gpu_hour"] = 8
        config = load_config(None)
        config.setdefault("output", {})["max_quote_rows_in_valuation_json"] = 1
        result = builder.run(config)
        self.assertNotIn("q01", [q["id"] for q in result["quotes"]["rows"]])
        self.assertEqual(
            result["cross_checks"]["current_flexible_reference_ask_usd_per_gpu_hour"], 5.2
        )
        self.assertIn(
            "above the comparable current", render_report(json.loads(render_json(result)))
        )

    def test_full_default_stress_does_not_discard_identified_main_valuation(self):
        builder = CaseBuilder(self)
        builder.case["reservation"]["delivery_end"] = "2027-02-01T00:00:00Z"
        config = load_config(None)
        config["sensitivities"]["default_probabilities"] = [0, 1]
        result = builder.run(config)
        self.assertTrue(result["valuation"]["identified"])
        stress = result["sensitivities"]["default_probability"][-1]
        self.assertEqual(stress["mark_adjusted_usd"], 0)
        self.assertFalse(stress["fair_fixed_price_identified"])
        self.assertIsNone(stress["fair_fixed_price_usd_per_gpu_hour"])
        json.loads(render_json(result))
        self.assertIn("n/a", render_report(result))

    def test_main_zero_survival_keeps_known_zero_mark_without_inventing_fair_price(self):
        builder = CaseBuilder(self)
        builder.case["reservation"]["delivery_end"] = "2027-02-01T00:00:00Z"
        builder.case["economics"]["provider_default_probability_over_deal"] = 1
        result = builder.run()
        val = result["valuation"]
        self.assertEqual(val["buyer_mark"]["default_and_sla_adjusted_usd"], 0)
        self.assertFalse(val["fair_fixed_price_identified"])
        self.assertIsNone(val["fair_fixed_price_usd_per_gpu_hour"]["mid"])
        self.assertEqual(val["decision"], "indifferent_unidentified_price")
        self.assertIn("no surviving service/payment exposure", render_report(result))
        json.loads(render_json(result))
