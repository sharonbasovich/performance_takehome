"""Current public manifest must bind real measurements without inventing a gain."""

from __future__ import annotations

import csv
import hashlib
import json
import unittest
from collections import Counter

from . import _paths

TASK = _paths.HARNESS_DIR.parent
CURRENT = json.loads((TASK / "submission.json").read_text(encoding="utf-8"))
EVIDENCE = _paths.REPO_ROOT / CURRENT["evidence"]["directory"]
SELECTED = "sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d"
GATES = {
    "all_requests_succeeded",
    "valid_finish_reason",
    "complete_output",
    "token_count_matches_usage",
    "greedy_self_consistency",
    "golden_output_match",
}


def load(relative):
    return json.loads((EVIDENCE / relative).read_text(encoding="utf-8"))


class CurrentDeliveryManifestTests(unittest.TestCase):
    def test_historical_manifest_bytes_and_assertions_are_preserved(self):
        local = (TASK / "submission.live-mi355x-20261026.json").read_bytes()
        git = (TASK / "submission.live-mi355x-20261026.git.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(local).hexdigest(),
            "c8d39e3d6ef4afa017e18e45456ea9338a616e08082b193db840a282412bd07e",
        )
        self.assertEqual(
            hashlib.sha256(git).hexdigest(),
            "0fe246c21b0d88026cb0fa34d304090aaeda7991cf8e48718da5f600b8e41d2a",
        )
        self.assertEqual(json.loads(local), json.loads(git))
        self.assertEqual(json.loads(local)["image_identity_kind"], "image-index-digest")
        self.assertFalse(json.loads(local)["delivery"]["registry_publication_verified"])

    def test_every_verbatim_evidence_and_source_hash_matches(self):
        inventory = load("inventory.json")["files"]
        for relative, expected in inventory.items():
            with self.subTest(relative=relative):
                path = EVIDENCE / relative
                self.assertTrue(path.resolve().is_relative_to(EVIDENCE.resolve()))
                raw = path.read_bytes()
                self.assertEqual(len(raw), expected["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected["sha256"])
        profile = EVIDENCE / "actual-source/development-benchmark.llmd.json"
        self.assertEqual(
            hashlib.sha256(profile.read_bytes()).hexdigest(),
            CURRENT["development_benchmark"]["sha256"],
        )
        self.assertEqual(
            CURRENT["development_benchmark"]["sha256"],
            load("baseline/result.json")["profile_sha256"],
        )

    def test_three_complete_phases_have_30_actual_requests_six_gates_and_golden_outputs(self):
        golden = load("baseline/golden.json")
        self.assertEqual(len(golden), 6)
        total = 0
        for phase in ("baseline", "control", "selected-final"):
            with self.subTest(phase=phase):
                declared = CURRENT["evidence"]["phases"][phase]
                report = load(declared["report"])
                durable = [
                    json.loads(line)
                    for line in (EVIDENCE / declared["traces"]).read_text().splitlines()
                ]
                self.assertEqual(declared["requests"], 30)
                self.assertEqual(len(report["traces"]), 30)
                self.assertEqual(len(durable), 31)
                self.assertEqual(durable[1:], report["traces"])
                self.assertTrue(report["gates_passed"])
                self.assertEqual({gate["name"] for gate in report["gates"]}, GATES)
                self.assertTrue(all(gate["passed"] for gate in report["gates"]))
                self.assertEqual(
                    Counter(t["prompt_id"] for t in report["traces"]), dict.fromkeys(golden, 5)
                )
                self.assertTrue(
                    all(t["ok"] and t["text"] == golden[t["prompt_id"]] for t in report["traces"])
                )
                total += len(report["traces"])
        self.assertEqual(total, CURRENT["evidence"]["measured_requests_total"])
        self.assertEqual(total, 90)

    def test_failed_candidate_has_no_fabricated_report_or_metric(self):
        candidate = CURRENT["evidence"]["phases"]["candidate"]
        self.assertEqual(candidate["status"], "PARTIAL_FAILURE")
        self.assertEqual(candidate["requests"], 0)
        self.assertIsNone(candidate["gates_passed"])
        self.assertIsNone(candidate["report"])
        self.assertFalse((EVIDENCE / "candidate/full-report.json").exists())
        self.assertEqual((EVIDENCE / candidate["traces"]).read_bytes(), b"")
        log = (EVIDENCE / "candidate/container.stderr").read_text()
        self.assertIn("Resolving DFlash model repo", log)
        self.assertIn("error: FileNotFound", log)
        decision = load("paired-result.json")["decision"]
        self.assertEqual(decision, CURRENT["evidence"]["decision"])
        self.assertEqual(decision["outcome"], "gate_failed")
        self.assertFalse(decision["kept"])
        with (EVIDENCE / "results.tsv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(
            [r["phase"] for r in rows], ["baseline", "control", "candidate", "selected-final"]
        )
        self.assertEqual(rows[2]["measured_requests"], "0")
        self.assertEqual(rows[2]["startup_s"], "")
        self.assertEqual(rows[2]["gates_passed"], "")

    def test_selected_manifest_and_rejected_config_identities_are_distinct(self):
        self.assertEqual(CURRENT["image_digest"], SELECTED)
        self.assertEqual(
            CURRENT["image"], "ghcr.io/sharonbasovich/performance_takehome-task2-llmd@" + SELECTED
        )
        self.assertEqual(CURRENT["image_identity_kind"], "linux-amd64-platform-manifest-digest")
        self.assertEqual(load("selected-image-inspect.json")[0]["Id"], SELECTED)
        self.assertEqual(CURRENT["delivery"]["platform_manifest"], SELECTED)
        manifest_raw = (EVIDENCE / "candidate-metadata/manifest.json").read_bytes()
        config_raw = (EVIDENCE / "candidate-metadata/config.json").read_bytes()
        candidate_id = "sha256:" + hashlib.sha256(manifest_raw).hexdigest()
        self.assertEqual(candidate_id, CURRENT["agent_harness"]["candidate_image_id"])
        self.assertNotEqual(candidate_id, SELECTED)
        candidate = json.loads(manifest_raw)
        self.assertEqual(
            candidate["config"]["digest"], "sha256:" + hashlib.sha256(config_raw).hexdigest()
        )
        self.assertEqual(len(candidate["layers"]), 23)
        config = json.loads(config_raw)
        selected = load("selected-image-inspect.json")[0]
        self.assertEqual(config["rootfs"]["diff_ids"], selected["RootFS"]["Layers"])
        self.assertEqual(config["config"]["Entrypoint"], selected["Config"]["Entrypoint"])
        self.assertEqual(
            config["config"]["Cmd"],
            selected["Config"]["Cmd"] + ["--speculative-drafter-model=native"],
        )
        self.assertEqual(
            hashlib.sha256((EVIDENCE / "pi/candidate.Dockerfile").read_bytes()).hexdigest(),
            CURRENT["agent_harness"]["candidate_Dockerfile_sha256"],
        )

    def test_current_provenance_does_not_claim_gain_or_unattended_execution(self):
        self.assertFalse(CURRENT["evidence"]["optimization_gain_claimed"])
        self.assertFalse(CURRENT["evaluation"]["optimization_or_speedup_claimed"])
        self.assertFalse(CURRENT["agent_harness"]["candidate_selected"])
        self.assertFalse(CURRENT["agent_harness"]["canonical_unattended_loop_executed"])
        self.assertEqual(
            CURRENT["agent_harness"]["execution_scope"], "external_stage_orchestration"
        )
        self.assertEqual(
            CURRENT["development_benchmark"]["request_profile"], "llmd_closed_thinking_v1"
        )
        self.assertFalse(CURRENT["development_benchmark"]["official_grade"])

    def test_successful_pi_metadata_excludes_message_and_argument_contents(self):
        metadata = load("pi/tool-events.json")
        self.assertEqual(metadata["stock_cli"]["version"], "1.0.0")
        self.assertEqual(metadata["effective_historical_wire_output_tokens"], 8192)
        self.assertEqual(metadata["requested_output_tokens"], 16384)
        starts = [e for e in metadata["tool_events"] if e["event"] == "tool_execution_start"]
        ends = [e for e in metadata["tool_events"] if e["event"] == "tool_execution_end"]
        self.assertEqual(len(starts), 10)
        self.assertEqual({e["tool_call_id"] for e in starts}, {e["tool_call_id"] for e in ends})
        allowed = {
            "sequence",
            "event",
            "tool_call_id",
            "tool_name",
            "is_error",
            "argument_canonical_utf8_bytes",
            "argument_canonical_sha256",
            "allowed_relative_work_filenames",
        }
        self.assertTrue(all(set(e) <= allowed for e in metadata["tool_events"]))
        self.assertEqual(metadata["assistant_stop_reason_metadata"][-1]["stop_reason"], "stop")
        self.assertEqual(
            load("pi/runtime-verification.json")["pi_distribution_files_checked"], 1243
        )

    def test_later_pi_proposal_remains_unmeasured(self):
        (pending,) = CURRENT["pending_proposals"]
        self.assertEqual(pending["status"], "UNMEASURED_PROPOSAL_ONLY")
        self.assertFalse(pending["GPU_build_or_measurement_performed"])
        self.assertFalse(pending["selected"])
        self.assertFalse(pending["speedup_claimed"])
        self.assertIsNone(pending["candidate_image_id"])
        dockerfile = (EVIDENCE / "later-unmeasured-pi2/candidate.Dockerfile").read_text()
        self.assertIn('"--page-chunk-size=64"', dockerfile)
        self.assertNotIn('"--speculative-drafter-model=native"', dockerfile)


if __name__ == "__main__":
    unittest.main()
