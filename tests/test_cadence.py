from contextlib import closing
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from renmon.features.monitoring.cadence import Cadence, divisors
from renmon.features.monitoring.service import Monitor
from renmon.profile import Profile


def signal(code, request):
    return SimpleNamespace(code=code, request=request)


class CadenceTests(unittest.TestCase):
    def test_schedule_shared_did_and_changed_rate(self):
        signals = [signal("a", "1"), signal("b", "2"), signal("c", "2")]
        cadence = Cadence()
        history = []
        for tick in range(11):
            due = cadence.due(signals, {"a": 1, "b": 3, "c": 10})
            history.append([s.code for s in due])
            cadence.advance(due)
        self.assertEqual(
            [i for i, codes in enumerate(history) if "b" in codes], [0, 3, 6, 9]
        )
        self.assertTrue(all(("b" in codes) == ("c" in codes) for codes in history))
        self.assertTrue(all("a" in codes for codes in history))
        self.assertEqual(len(cadence.due(signals, {"a": 1, "b": 5, "c": 10})), 3)

    def test_new_selection_immediate_and_no_advance_on_missing_connection(self):
        s = signal("a", "1")
        cadence = Cadence()
        self.assertEqual(cadence.due([s], {"a": 10}), [s])
        self.assertEqual(cadence.due([s], {"a": 10}), [s])
        cadence.advance([s])
        self.assertEqual(cadence.due([s], {"a": 10}), [])
        cadence.due([], {})
        self.assertEqual(cadence.due([s], {"a": 10}), [s])

    def test_validation(self):
        self.assertEqual(divisors({}, ["a"]), {"a": 1})
        for value in [True, 0, 4, 15, 2.0, "3"]:
            with self.assertRaises(ValueError):
                divisors({"a": value}, ["a"])
        with self.assertRaises(ValueError):
            divisors({"b": 3}, ["a"])

    def test_demo_sparse_samples_csv_and_live_change(self):
        from renmon.features.history.export import export_csv
        import sqlite3

        profile = Profile.load(
            Path(__file__).resolve().parents[1] / "profiles/11075.json"
        )
        with tempfile.TemporaryDirectory() as folder:
            monitor = Monitor(profile, log_dir=folder)
            try:
                monitor.start(
                    dict(
                        mode="demo",
                        codes=["PR064", "PR383"],
                        interval=0.1,
                        divisors={"PR064": 1, "PR383": 5},
                    )
                )
                deadline = time.monotonic() + 3
                while len(monitor.samples) < 7 and time.monotonic() < deadline:
                    time.sleep(0.01)
                samples = monitor.snapshot()["samples"]
                self.assertGreaterEqual(len(samples), 7)
                self.assertEqual(
                    [i for i, s in enumerate(samples[:7]) if "PR383" in s["values"]],
                    [0, 5],
                )
                monitor.update_divisor({"code": "PR383", "divisor": 1})
                time.sleep(0.25)
                monitor.stop()
                monitor.thread.join(2)
                snapshot = monitor.snapshot()
                self.assertIn("PR383", snapshot["samples"][-1]["values"])
                count = sum(len(s["values"]) for s in snapshot["samples"])
                with closing(sqlite3.connect(snapshot["log_path"])) as db:
                    self.assertEqual(
                        db.execute("select count(*) from reading").fetchone()[0], count
                    )
                self.assertEqual(
                    len(export_csv(snapshot).decode("utf-8-sig").splitlines()) - 1,
                    count,
                )
            finally:
                monitor.close()
