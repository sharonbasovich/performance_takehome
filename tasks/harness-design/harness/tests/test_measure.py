"""Measurement edge cases: malformed benchmark files and servers that are up but broken."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from abstract_harness import measure
from abstract_harness.decision import decide

from . import _paths

BENCHMARK = _paths.REPO_ROOT / "tasks" / "harness-design" / "harness" / "development-benchmark.json"


class FluidRateBoundaryTest(unittest.TestCase):
    def test_slow_decode_cannot_be_kept_for_faster_first_token(self) -> None:
        # Before conversion at the Etalon boundary these score ~0.99 vs ~6.24,
        # wrongly keeping a candidate with ten times slower token intervals.
        base = measure.RequestTrace("p", True, arrival_times_s=[1.0, 1.01, 1.02])
        candidate = measure.RequestTrace("p", True, arrival_times_s=[0.01, 0.11, 0.21])
        base_rate, _ = measure.ftgr_for_traces([base], {})
        candidate_rate, _ = measure.ftgr_for_traces([candidate], {})
        self.assertIsNotNone(base_rate)
        self.assertIsNotNone(candidate_rate)
        self.assertGreater(base_rate, 90.0)
        self.assertLess(candidate_rate, 11.0)
        decision = decide(
            {"ttft_s": {"p": [1.0] * 5}, "ftgr_tok_s": {"p": [base_rate] * 5}},
            {"ttft_s": {"p": [0.01] * 5}, "ftgr_tok_s": {"p": [candidate_rate] * 5}},
            gates_passed=True,
        )
        self.assertEqual(decision.outcome, "regressed")
        self.assertFalse(decision.kept)

    def test_first_token_offset_does_not_change_decode_rate(self) -> None:
        rates = []
        for offset in (0.1, 10.0):
            trace = measure.RequestTrace(
                "p", True, arrival_times_s=[offset, offset + 0.05, offset + 0.1]
            )
            rate, dropped = measure.ftgr_for_traces([trace], {})
            self.assertEqual(dropped, 0)
            self.assertIsNotNone(rate)
            rates.append(rate)
        self.assertAlmostEqual(rates[0], rates[1], places=8)

    def test_invalid_arrival_order_has_no_rate(self) -> None:
        trace = measure.RequestTrace("p", True, arrival_times_s=[0.2, 0.1])
        rate, _ = measure.ftgr_for_traces([trace], {})
        self.assertIsNone(rate)


class _BrokenEngine(BaseHTTPRequestHandler):
    """Serves /v1/models like a healthy engine but fails every completion with HTTP 500."""

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        body = json.dumps({"data": [{"id": "broken-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        body = b'{"error": "kv cache allocation failed"}'
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BenchmarkFileTest(unittest.TestCase):
    def test_zero_prompts_is_rejected(self) -> None:
        data = json.loads(BENCHMARK.read_text("utf-8"))
        data["prompts"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                measure.load_benchmark(path)
        self.assertIn("nonempty prompts", str(ctx.exception))

    def test_duplicate_prompt_ids_are_rejected(self) -> None:
        data = json.loads(BENCHMARK.read_text("utf-8"))
        data["prompts"].append(dict(data["prompts"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bench.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                measure.load_benchmark(path)

    def test_shipped_benchmark_loads(self) -> None:
        data = measure.load_benchmark(BENCHMARK)
        self.assertGreaterEqual(len(data["prompts"]), 2)
        self.assertGreaterEqual(int(data["repetitions"]), 3)


class BrokenServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _BrokenEngine)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.benchmark = measure.load_benchmark(BENCHMARK)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_ready_but_every_completion_fails_is_a_startup_error(self) -> None:
        start = time.monotonic()
        with self.assertRaises(measure.MeasurementError) as ctx:
            measure.wait_for_first_valid_generation(
                self.base_url, start, self.benchmark, timeout_s=3.0
            )
        self.assertLess(time.monotonic() - start, 10.0)
        self.assertIn("HTTP 500", str(ctx.exception))

    def test_readiness_reports_served_model_id(self) -> None:
        self.assertEqual(measure.wait_for_model_id(self.base_url, timeout_s=3.0), "broken-model")
