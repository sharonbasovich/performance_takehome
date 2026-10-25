"""Adversarial review regressions for complete calibration and failed streams."""

import json
import tempfile
import unittest
from pathlib import Path

import httpx
from audit_timing import audit
from bench.calibration import CalibrationError, calibrate
from bench.gates import judge
from bench.plan import plan_digest
from bench.prompts import make_prompt
from bench.records import Evidence, RequestRecord, RunRecord
from runner.run import RequestMeta, Runner, parse_args

from tests import test_calibration_capture as fixtures
from tests.helpers import SUITE, make_run, plan


class CompleteCalibrationTests(unittest.TestCase):
    def test_missing_warmup_cannot_freeze_complete_measurement_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path, events, run, _ = fixtures.CalibrationEvidenceTests().evidence(Path(temp))
            workload = json.loads(path.read_text())
            workload["warmup"]["requests_per_cell"] = 1
            path.write_text(json.dumps(workload))
            run["plan"]["digest"] = plan_digest(path)
            run["planned_startup_launches"] = 1
            run["units"][0]["planned_warmup"] = 1
            (events / "run.json").write_text(json.dumps(run))
            with self.assertRaisesRegex(CalibrationError, "warmup"):
                calibrate(path, events, allow_mock=True)

    def test_missing_startup_cannot_freeze_complete_measurement_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path, events, run, _ = fixtures.CalibrationEvidenceTests().evidence(Path(temp))
            run["startup"] = []
            run["planned_startup_launches"] = 1
            (events / "run.json").write_text(json.dumps(run))
            with self.assertRaisesRegex(CalibrationError, "startup"):
                calibrate(path, events, allow_mock=True)

    def test_calibration_launch_count_is_checked_against_the_frozen_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            path, events, run, _ = fixtures.CalibrationEvidenceTests().evidence(Path(temp))
            workload = json.loads(path.read_text())
            workload["modes"]["calibration"]["startup_launches"] = 2
            path.write_text(json.dumps(workload))
            run["plan"]["digest"] = plan_digest(path)
            run["planned_startup_launches"] = 1
            (events / "run.json").write_text(json.dumps(run))
            with self.assertRaisesRegex(CalibrationError, "launch count"):
                calibrate(path, events, allow_mock=True)


class MalformedStreamAuditTests(unittest.IsolatedAsyncioTestCase):
    async def record(self, payload):
        return await self.record_raw(json.dumps(payload))

    async def record_raw(self, raw):
        body = ("data: " + raw + "\n\ndata: [DONE]\n\n").encode()

        class Bytes(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield body

        workload = plan()
        with tempfile.TemporaryDirectory() as temp:
            args = parse_args(
                [
                    "--plan",
                    str(SUITE / "fixtures/workload.mock.json"),
                    "--out",
                    temp,
                    "--assume-mock",
                ]
            )
            runner = Runner(args, workload)
            transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=Bytes()))
            async with httpx.AsyncClient(transport=transport) as client:
                return await runner.execute(
                    client,
                    make_prompt(workload, "chat_short", "x", 0, 0),
                    RequestMeta("x", None, "startup_probe", "startup", 0),
                )

    async def test_rejected_chunks_remain_trustworthy_failed_request_evidence(self):
        cases = [
            {"choices": [{"delta": {"content": "must not count"}, "finish_reason": "stop"}, {}]},
            {"choices": {"0": {"delta": {"content": "bad"}}}},
            {"choices": ["not an object"]},
            {"choices": [{"index": 1, "delta": {"content": "bad"}}]},
            {"choices": [{"delta": None}]},
            {"choices": [{"delta": {"content": ["not text"]}}]},
            {"choices": [{"delta": {"reasoning_content": "also discarded", "content": 4}}]},
            {"choices": [{"delta": {"content": "also discarded", "reasoning_content": 4}}]},
            ["not a payload object"],
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                record = await self.record(payload)
                self.assertEqual(record["error"]["kind"], "protocol")
                run = make_run([record])
                result = audit(
                    Evidence(Path("."), RunRecord(run), [RequestRecord(record)], [], "native")
                )
                self.assertEqual(result["status"], "PASS", result["failures"])
                self.assertEqual(result["requests"][0]["protocol_faults"], 1)
                self.assertEqual(result["requests"][0]["ttft_s"], None)

    async def test_finish_convenience_value_matches_recorder_without_hiding_raw_faults(self):
        record = await self.record({"choices": [{"delta": {}, "finish_reason": 7}]})
        self.assertEqual(record["finish_reason"], "7")
        result = audit(
            Evidence(
                Path("."), RunRecord(make_run([record])), [RequestRecord(record)], [], "native"
            )
        )
        self.assertEqual(result["status"], "PASS", result["failures"])

    async def test_error_envelope_never_contributes_valid_looking_text_or_finish(self):
        for error in (None, {}, {"message": "failed"}):
            with self.subTest(error=error):
                record = await self.record(
                    {
                        "error": error,
                        "choices": [{"delta": {"content": "discarded"}, "finish_reason": "stop"}],
                    }
                )
                self.assertEqual(record["error"]["kind"], "protocol")
                self.assertEqual(record["text"]["content"], "")
                self.assertIsNone(record["finish_reason"])
                result = audit(
                    Evidence(
                        Path("."),
                        RunRecord(make_run([record])),
                        [RequestRecord(record)],
                        [],
                        "native",
                    )
                )
                self.assertEqual(result["status"], "PASS", result["failures"])
                self.assertEqual(result["requests"][0]["protocol_faults"], 1)

    async def test_bounded_json_parser_limits_preserve_failed_request_evidence(self):
        payloads = [
            '{"nested":' + "[" * 10000 + "0" + "]" * 10000 + "}",
            '{"unused_integer":' + "9" * 5000 + "}",
        ]
        for raw in payloads:
            with self.subTest(bytes=len(raw)):
                record = await self.record_raw(raw)
                self.assertEqual(record["error"]["kind"], "protocol")
                self.assertEqual(record["events"][0]["raw"], raw)
                self.assertEqual(judge(record, plan(), []).category, "failed")
                result = audit(
                    Evidence(
                        Path("."),
                        RunRecord(make_run([record])),
                        [RequestRecord(record)],
                        [],
                        "native",
                    )
                )
                self.assertEqual(result["status"], "PASS", result["failures"])
                self.assertEqual(result["requests"][0]["protocol_faults"], 1)


if __name__ == "__main__":
    unittest.main()
