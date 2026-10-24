"""Reservation arithmetic: hours, fees, discounting, SLA, default, mark and decision."""

import unittest

from research.months import parse_utc
from research.valuation import discount_factor, survival_probability

from .support import CaseBuilder, run_demo


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.results = run_demo()
        self.val = self.results["valuation"]

    def test_reserved_hours_from_calendar(self):
        self.assertEqual(self.val["reserved_hours"], 744 + 672 + 744)
        self.assertEqual([m["reserved_hours"] for m in self.val["months"]], [744, 672, 744])
        self.assertEqual(
            [m["delivery_month"] for m in self.val["months"]], ["2027-01", "2027-02", "2027-03"]
        )

    def test_gpu_count_scales_hours(self):
        b = CaseBuilder(self)
        b.case["reservation"]["gpu_count"] = 4
        self.assertEqual(b.run()["valuation"]["reserved_hours"], 4 * 2160)

    def test_fees_are_price_times_reserved_hours(self):
        self.assertEqual(self.val["fees_total_usd"], 4.5 * 2160)
        self.assertEqual([m["fee_usd"] for m in self.val["months"]], [3348.0, 3024.0, 3348.0])

    def test_expected_usage_does_not_reduce_fees(self):
        b = CaseBuilder(self)
        b.case["reservation"]["expected_buyer_used_fraction"] = 0.2
        other = b.run()["valuation"]
        self.assertEqual(other["fees_total_usd"], self.val["fees_total_usd"])
        self.assertEqual(other["buyer_mark"], self.val["buyer_mark"])
        info = self.val["usage_is_informational_only"]
        self.assertEqual(info["fees_owed_usd"], 9720.0)
        self.assertEqual(info["WRONG_fees_scaled_by_usage_usd"], 6318.0)
        self.assertAlmostEqual(info["effective_usd_per_used_gpu_hour"], 4.5 / 0.65, places=4)

    def test_payment_dates_are_month_ends_in_arrears(self):
        self.assertEqual(
            [m["payment_date"] for m in self.val["months"]],
            ["2027-02-01T00:00:00Z", "2027-03-01T00:00:00Z", "2027-04-01T00:00:00Z"],
        )

    def test_discounting_reconciles(self):
        as_of = parse_utc(self.results["as_of"])
        for m in self.val["months"]:
            df = discount_factor(0.05, as_of, parse_utc(m["payment_date"]))
            self.assertAlmostEqual(m["discount_factor"], df, places=8)
            self.assertAlmostEqual(
                m["value_discounted_usd"], round(m["value_undiscounted_usd"] * df, 2), places=1
            )
            undiscounted = (m["fair_value_usd_per_gpu_hour"]["mid"] - 4.5) * m["reserved_hours"]
            self.assertAlmostEqual(m["value_undiscounted_usd"], undiscounted, places=1)
        self.assertAlmostEqual(
            self.val["buyer_mark"]["discounted_usd"],
            sum(m["value_discounted_usd"] for m in self.val["months"]),
            places=1,
        )
        self.assertAlmostEqual(
            self.val["buyer_mark"]["default_and_sla_adjusted_usd"],
            sum(m["value_adjusted_usd"] for m in self.val["months"]),
            places=1,
        )
        self.assertAlmostEqual(
            self.val["buyer_mark"]["per_reserved_gpu_hour_usd"],
            self.val["buyer_mark"]["default_and_sla_adjusted_usd"] / 2160,
            places=5,
        )

    def test_sla_and_default_adjustments(self):
        for m in self.val["months"]:
            self.assertAlmostEqual(m["availability"], 0.999)
        self.assertEqual(self.val["months"][-1]["survival_probability"], 0.98)
        surv = [m["survival_probability"] for m in self.val["months"]]
        self.assertEqual(surv, sorted(surv, reverse=True))
        self.assertAlmostEqual(
            self.val["buyer_mark"]["sla_adjusted_usd"],
            self.val["buyer_mark"]["discounted_usd"] * 0.999,
            places=1,
        )
        self.assertLess(
            abs(self.val["buyer_mark"]["default_and_sla_adjusted_usd"]),
            abs(self.val["buyer_mark"]["sla_adjusted_usd"]),
        )

    def test_zero_default_probability_leaves_sla_adjusted_mark(self):
        sens = {
            row["p_default"]: row["mark_adjusted_usd"]
            for row in self.results["sensitivities"]["default_probability"]
        }
        self.assertAlmostEqual(sens[0.0], self.val["buyer_mark"]["sla_adjusted_usd"], places=1)
        self.assertGreater(abs(sens[0.0]), abs(sens[0.1]))

    def test_sla_change_changes_availability(self):
        b = CaseBuilder(self)
        b.case["reservation"]["sla_pct"] = 99.0
        self.assertAlmostEqual(b.run()["valuation"]["months"][0]["availability"], 0.99)

    def test_fair_fixed_price_zeroes_the_mark(self):
        fair = self.val["fair_fixed_price_usd_per_gpu_hour"]["mid"]
        b = CaseBuilder(self)
        b.case["reservation"]["fixed_usd_per_gpu_hour"] = fair
        mark = b.run()["valuation"]["buyer_mark"]["default_and_sla_adjusted_usd"]
        self.assertAlmostEqual(mark, 0.0, places=1)

    def test_decision_and_flip_conditions(self):
        self.assertEqual(self.val["decision"], "do_not_sign_at_this_price")
        self.assertLess(self.val["buyer_mark"]["default_and_sla_adjusted_usd"], 0)
        self.assertLess(self.val["buyer_mark"]["interval_usd"]["low"], 0)
        self.assertGreater(self.val["buyer_mark"]["interval_usd"]["high"], 0)
        self.assertGreater(self.val["scenario_fair_fixed_price_usd_per_gpu_hour"]["scarcity"], 4.5)
        self.assertLess(self.val["scenario_fair_fixed_price_usd_per_gpu_hour"]["base"], 4.5)
        self.assertGreater(self.val["scenario_marks_usd"]["scarcity"], 0)
        self.assertLess(
            self.val["scenario_marks_usd"]["cheap_compute"], self.val["scenario_marks_usd"]["base"]
        )

    def test_cheap_contract_price_flips_decision(self):
        b = CaseBuilder(self)
        b.case["reservation"]["fixed_usd_per_gpu_hour"] = 3.0
        self.assertEqual(b.run()["valuation"]["decision"], "sign")

    def test_discount_rate_sensitivity_direction(self):
        rows = {
            row["bump"]: row["mark_adjusted_usd"]
            for row in self.results["sensitivities"]["discount_rate_bump"]
        }
        self.assertGreater(rows[0.02], rows[0.0])
        self.assertGreater(rows[0.0], rows[-0.02])

    def test_unidentified_curve_yields_unidentified_mark(self):
        val = run_demo(exclude_quote_ids=("q04", "q05", "q06", "q07"))["valuation"]
        self.assertEqual(val["decision"], "unidentified")
        self.assertIsNone(val["buyer_mark"])
        self.assertEqual(val["reserved_hours"], 2160)
        self.assertEqual(val["fees_total_usd"], 9720.0)


class HelperTests(unittest.TestCase):
    def test_discount_factor(self):
        a, b = parse_utc("2026-10-01T00:00:00Z"), parse_utc("2027-10-01T00:00:00Z")
        self.assertAlmostEqual(discount_factor(0.05, a, b), 1 / 1.05)

    def test_survival_uniform_hazard(self):
        a, mid, b = (
            parse_utc(t)
            for t in ("2026-10-01T00:00:00Z", "2027-01-01T00:00:00Z", "2027-04-01T00:00:00Z")
        )
        self.assertAlmostEqual(survival_probability(0.02, a, b, b), 0.98)
        self.assertGreater(survival_probability(0.02, a, mid, b), 0.98)
        self.assertEqual(survival_probability(0.0, a, mid, b), 1.0)
