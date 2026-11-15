import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon.profile import Profile
from renmon.features.monitoring.service import Monitor
from renmon.features.monitoring.demo import demo_value

ROOT = Path(__file__).resolve().parents[1]


class StateTimingTests(unittest.TestCase):
    def test_regeneration_is_enum_not_boolean(self):
        state = Profile.load(ROOT / "profiles/11075.json").by_code(["ET824"])[0]
        for raw, expected in ((0, 2), (1, 3), (9, 11), (255, 0)):
            value = state.decode(bytes.fromhex("62246D") + bytes([raw]))
            self.assertEqual(value, expected)
            self.assertIn(str(int(value)), state.interpretations)
        self.assertIn("успішно", state.interpretations["3"]["description_uk"])
        self.assertNotIn(1, state.demo_states)  # ACTIVE is not emitted by this formula

    def test_demo_states_use_decoded_domain_and_are_stable(self):
        profile = Profile.load(ROOT / "profiles/11075.json")
        for s in profile.signals:
            if s.kind == "state":
                self.assertTrue(s.demo_states, s.code)
                for t in (0, 0.1, 6, 12, 60, 120):
                    value = demo_value(s, t)
                    self.assertIn(value, s.demo_states)
                    self.assertIn(str(int(value)), s.interpretations)
        state = profile.by_code(["ET824"])[0]
        self.assertEqual(demo_value(state, 0), demo_value(state, 0.2))

    def test_fast_demo_and_interval_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = Monitor(Profile.load(ROOT / "profiles/11075.json"), directory)
            try:
                for invalid in (0.09, float("nan"), 11):
                    with self.assertRaises(ValueError):
                        monitor.start(
                            dict(mode="demo", codes=["ET824"], interval=invalid)
                        )
                for interval in (0.1, 0.2):
                    monitor.start(dict(mode="demo", codes=["ET824"], interval=interval))
                    deadline = time.monotonic() + 2
                    while (
                        len(monitor.snapshot()["samples"]) < 5
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    monitor.stop()
                    monitor.thread.join(2)
                    state = monitor.snapshot()
                    samples = state["samples"]
                    self.assertGreaterEqual(len(samples), 5)
                    self.assertEqual(state["interval"], interval)
                    periods = [b["at"] - a["at"] for a, b in zip(samples, samples[1:])]
                    self.assertLess(sum(periods) / len(periods), interval + 0.07)
                    self.assertTrue(
                        all(s["requests"] == 0 and s["dids"] == 1 for s in samples)
                    )
            finally:
                monitor.stop()
                if monitor.thread:
                    monitor.thread.join(2)
                monitor.connection.close()


if __name__ == "__main__":
    unittest.main()
