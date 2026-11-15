import sys, threading, unittest, time, tempfile
from unittest.mock import patch
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon.performance import Performance, split_response
from renmon.elm import Elm, ElmError, NegativeResponse
from renmon.safety import SafetyError
from renmon.profile import Profile, Poller

ROOT = Path(__file__).resolve().parents[1]


class Wire:
    def __init__(self, reject=False):
        self.commands = []
        self.pending = b""
        self.reject = reject

    def reset_input(self):
        self.pending = b""

    def write(self, data):
        cmd = data.decode().strip()
        self.commands.append(cmd)
        if len(cmd) > 6 and self.reject:
            response = "7F2213"
        else:
            response = "62" + "".join(
                cmd[i : i + 4] + "0001" for i in range(2, len(cmd), 4)
            )
        self.pending = (response + "\r>").encode()

    def read(self, size):
        out, self.pending = self.pending[:size], self.pending[size:]
        return out


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.requests = [
            "222001",
            "222005",
            "222801",
            "22242C",
            "22240D",
            "22246D",
            "2224A9",
            "222407",
        ]
        self.lengths = {r[2:]: 2 for r in self.requests}

    def test_eight_dids_become_three_exchanges_after_baseline(self):
        wire = Wire()
        elm = Elm(wire)
        p = Performance(self.lengths, True)
        first, errors = p.read(elm, self.requests)
        self.assertFalse(errors)
        self.assertEqual(p.requests, 8)
        second, errors = p.read(elm, self.requests)
        self.assertFalse(errors)
        self.assertEqual(p.requests, 3)
        self.assertEqual(first, second)
        self.assertEqual(p.snapshot()["status"], "active")
        self.assertEqual(
            wire.commands[-3:], ["22200120052801", "22242C240D246D", "2224A92407"]
        )
        with self.assertRaises(SafetyError):
            elm.send("2220012005")

    def test_off_remains_single_and_duplicate_signals_share_did(self):
        profile = Profile.load(ROOT / "profiles/11075.json")
        wire = Wire()
        elm = Elm(wire)
        p = Performance(self.lengths, False)
        p.read(elm, self.requests)
        p.read(elm, self.requests)
        self.assertEqual(len(wire.commands), 16)
        self.assertEqual(p.snapshot()["status"], "off")
        poller = Poller(elm, profile.by_code(["PR064", "PR064"]), p)
        values, errors, _ = poller.cycle()
        self.assertEqual(p.requests, 1)
        self.assertFalse(errors)

    def test_rejection_disables_batches_without_immediate_retry(self):
        wire = Wire(reject=True)
        elm = Elm(wire)
        p = Performance(self.lengths, True)
        p.read(elm, self.requests)
        values, errors = p.read(elm, self.requests)
        self.assertFalse(values)
        self.assertEqual(len(errors), 8)
        self.assertEqual(p.requests, 1)
        self.assertEqual(p.snapshot()["status"], "fallback")
        self.assertIn("wrong message length", p.reason)
        values, errors = p.read(elm, self.requests)
        self.assertEqual(len(values), 8)
        self.assertFalse(errors)
        self.assertEqual(p.requests, 8)
        self.assertFalse(elm._approved_multi)

    def test_strict_response_validation(self):
        req = self.requests[:2]
        for data in [
            "622001000120050001FF",
            "622005000120010001",
            "6220010001",
            "622001000120010001",
            "612001000120050001",
            "7F2213",
        ]:
            with self.subTest(data=data), self.assertRaises(ElmError):
                split_response(bytes.fromhex(data), req, self.lengths)

    def test_indexed_reply_uses_declared_length_not_can_padding(self):
        elm = Elm(Wire())
        requests = ["222001", "22242C"]
        lengths = {"2001": 2, "242C": 2}
        # Nine payload bytes occupy six bytes in the first frame plus seven
        # in the last one. CAF1 may retain those four padding bytes.
        for tail in ["2C04D2", "2C04D2AAAAAAAA"]:
            payload = elm._parse("009\r0:622001000124\r1:" + tail + "\r")
            parts = split_response(payload, requests, lengths)
            self.assertEqual(parts["22242C"], bytes.fromhex("62242C04D2"))
        for raw in [
            "009\r0:622001000124\r1:2C04",  # truncated
            "009\r0:622001000124\r1:2C04D2AA",  # not a full padded frame
            "008\r0:622001000124\r1:2C04D2",  # inconsistent declaration
        ]:
            with self.subTest(raw=raw), self.assertRaises(ElmError):
                elm._parse(raw)
        # Without an explicit length, extra bytes remain an error.
        with self.assertRaises(ElmError):
            split_response(elm._parse("6220010001242C04D2AA"), requests, lengths)

    def test_new_selection_gets_single_read_first_and_stop(self):
        wire = Wire()
        elm = Elm(wire)
        p = Performance(self.lengths, True)
        p.read(elm, self.requests[:2])
        p.read(elm, self.requests[:3])
        self.assertEqual(wire.commands[-2:], ["2220012005", "222801"])
        stop = threading.Event()
        stop.set()
        p.read(elm, self.requests, stop)
        self.assertEqual(p.requests, 0)

    def test_missing_wrong_length_and_range_dids_stay_single(self):
        wire = Wire()
        elm = Elm(wire)
        p = Performance({"2001": 1, "2000": 2}, True)
        req = ["222001", "222005", "222000"]
        p.read(elm, req)
        p.read(elm, req)
        self.assertFalse(p.validated)
        self.assertEqual(p.requests, 3)

    def test_timeout_disables_batch_and_does_not_replay(self):
        elm = Mock()
        p = Performance(self.lengths, True)
        p.validated = set(self.requests)
        elm.request_many.side_effect = ElmError("timeout")
        p.read(elm, self.requests)
        elm.request_many.assert_called_once()
        elm.request.assert_not_called()
        self.assertTrue(p.failed)

    def test_rejects_long_duplicate_or_nonread_groups(self):
        elm = Elm(Wire())
        for requests in [
            self.requests[:4],
            ["222001", "222001"],
            ["222001", "1101"],
            ["222001"],
            ["222001", "222005\r1101"],
        ]:
            with self.assertRaises(SafetyError):
                elm.request_many(requests)
        self.assertFalse(elm._approved_multi)

    def test_monitor_integration_and_reconnect_revalidates(self):
        from renmon.features.monitoring.service import Monitor

        class Adapter(Wire):
            def write(self, data):
                cmd = data.decode().strip()
                if cmd.startswith("AT") or cmd == "2180":
                    self.commands.append(cmd)
                    response = (
                        "618000000000000100000000000000000003"
                        if cmd == "2180"
                        else "ELM327"
                        if cmd == "ATI"
                        else "OK"
                    )
                    self.pending = (response + "\r>").encode()
                else:
                    super().write(data)

            def close(self):
                pass

        adapter = Adapter()
        with (
            tempfile.TemporaryDirectory() as logs,
            patch("renmon.features.monitoring.service.ports", return_value=["COM12"]),
            patch("renmon.features.connection.service.sys.platform", "win32"),
            patch(
                "renmon.features.connection.service.SerialTransport",
                return_value=adapter,
            ),
        ):
            mon = Monitor(Profile.load(ROOT / "profiles/11075.json"), log_dir=logs)
            try:
                mon.start(
                    dict(
                        mode="live",
                        port="COM12",
                        codes=["PR064", "PR071", "PR038"],
                        interval=0.1,
                        performance=True,
                    )
                )
                deadline = time.monotonic() + 4
                while len(mon.samples) < 3 and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertGreaterEqual(len(mon.samples), 3, mon.error)
                self.assertEqual(mon.samples[0]["requests"], 3)
                self.assertEqual(mon.samples[-1]["requests"], 1)
                with mon.connection.lock:
                    mark = len(adapter.commands)
                    mon.connection.generation += 1
                deadline = time.monotonic() + 3
                while (
                    adapter.commands[mark:].count("2180") < 1
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                time.sleep(0.2)
                commands = adapter.commands[mark:]
                at = commands.index("2180")
                self.assertEqual(
                    commands[at + 1 : at + 4], ["222001", "222005", "222801"]
                )
            finally:
                mon.stop()
                mon.thread.join(3)
                mon.connection.close()


if __name__ == "__main__":
    unittest.main()
