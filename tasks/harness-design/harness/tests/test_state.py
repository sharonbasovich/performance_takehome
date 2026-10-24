"""On-disk state round-trips so a restarted process can resume."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from abstract_harness.state import HarnessState, ImageRef, InProgress, load_state, save_state

from . import _paths  # noqa: F401


class StateTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        state = HarnessState(
            engine="standin",
            source_commit="abc",
            lease_start_ts=1.0,
            attempt_index=3,
            api_usd_cumulative=0.25,
            last_good=ImageRef(tag="x:last-good", digest="sha256:" + "0" * 64, experiment="001-a"),
            baseline_samples={"ttft_s": {"p": [0.1, 0.2]}},
            golden={"p": "hello"},
            in_progress=InProgress(
                experiment="004-b", hypothesis="h", started_ts=2.0, patch_path="p", stage="building"
            ),
            history=[{"experiment": "001-a", "outcome": "improved"}],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_state(path, state)
            loaded = load_state(path)
            self.assertEqual(loaded, state)
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)
            self.assertFalse(list(Path(tmp).glob("*.tmp*")), "atomic write leaves no temp files")

    def test_missing_state_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_state(Path(tmp) / "nope.json"))


if __name__ == "__main__":
    unittest.main()
