import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon.connection import Connection
from renmon.decode import DecodeError
from renmon.elm import Elm, ElmError
from renmon.features.monitoring.service import Monitor
from renmon.profile import Profile
from renmon.safety import SafetyError

if sys.platform != "win32":
    from fake_elm import FakeElm
from renmon.transport import SerialTransport

ROOT = Path(__file__).resolve().parents[1]


class NoWrite:
    def write(self, data):
        raise AssertionError("Blocked command reached transport")

    def reset_input(self):
        raise AssertionError("Blocked command reached transport")


class SafetyTests(unittest.TestCase):
    def test_blocked_at_transport_boundary(self):
        elm = Elm(NoWrite())
        for command in (
            "2EF1900000",
            "3101FF00",
            "14FFFFFF",
            "1101",
            "2701",
            "1002",
            "1086",
            "AT SH 7DF\r2EF19000",
            "22F190\n1101",
            "",
            "ATMA",
            "ATSH7DF",
            "ATSH7DF\x00",
            "2200010002",
        ):
            for method in (elm.send, elm.request, elm.raw):
                with (
                    self.subTest(command=command, method=method.__name__),
                    self.assertRaises(SafetyError),
                ):
                    method(command)

    def test_bluetooth_ready_retry(self):
        elm = Elm(NoWrite())
        stop = unittest.mock.Mock()
        stop.is_set.return_value = False
        stop.wait.return_value = False
        with patch.object(
            elm, "identify", side_effect=[ElmError("timeout"), "ELM327"]
        ) as identify:
            self.assertEqual(elm.wait_ready(stop), "ELM327")
            self.assertEqual(identify.call_count, 2)
        with patch.object(elm, "identify", side_effect=ElmError("timeout")) as identify:
            with self.assertRaises(ElmError):
                elm.wait_ready(stop)
            self.assertEqual(identify.call_count, 3)

    @unittest.skipIf(sys.platform == "win32", "PTY emulator requires POSIX")
    def test_delayed_adapter_identification(self):
        class SlowAdapter(FakeElm):
            def _reply(self, line):
                if line.strip().upper().replace(" ", "") == "ATI":
                    time.sleep(1.8)
                return super()._reply(line)

        fake = SlowAdapter({})
        connection = Connection()
        try:
            connection.select(fake.device, auto_connect=True)
            deadline = time.monotonic() + 7
            while connection.status != "connected" and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(connection.status, "connected", connection.error)
            self.assertEqual(connection.generation, 1)
        finally:
            connection.close()
            fake.close()

    def test_reply_identity(self):
        signal = Profile.load(ROOT / "profiles/11075.json").by_code(["PR383"])[0]
        for payload in ("62242D04D2", "50242C04D2", "62242C04"):
            with self.assertRaises(DecodeError):
                signal.decode(bytes.fromhex(payload))
        self.assertEqual(signal.decode(bytes.fromhex("62242C04D2")), 12.34)

    @unittest.skipIf(sys.platform == "win32", "PTY emulator requires POSIX")
    def test_live_worker_with_fake_serial(self):
        class CountingAdapter(FakeElm):
            ati_count = 0

            def _reply(self, line):
                if line.strip().upper().replace(" ", "") == "ATI":
                    self.ati_count += 1
                return super()._reply(line)

        fake = CountingAdapter(
            {
                "2180": bytes.fromhex("618000000000000100000000000000000003"),
                "22242C": bytes.fromhex("62242C04D2"),
                "222001": bytes.fromhex("6220010BB8"),
            }
        )
        monitor = Monitor(
            Profile.load(ROOT / "profiles/11075.json"),
            port_provider=lambda: [fake.device],
        )

        def transport(port, **kwargs):
            return SerialTransport(port, timeout=0.1)

        try:
            with (
                patch(
                    "renmon.features.monitoring.service.ports",
                    return_value=[fake.device],
                ),
                patch(
                    "renmon.features.connection.service.SerialTransport",
                    side_effect=transport,
                ) as opened,
            ):
                monitor.select_adapter({"port": fake.device, "auto_connect": True})
                monitor.start(
                    {
                        "mode": "live",
                        "port": fake.device,
                        "codes": ["PR383"],
                        "session": "10C0",
                        "interval": 0.5,
                    }
                )
                deadline = time.monotonic() + 5
                while not monitor.snapshot()["samples"] and time.monotonic() < deadline:
                    time.sleep(0.05)
                samples = monitor.snapshot()["samples"]
                self.assertTrue(samples, monitor.error)
                self.assertEqual(samples[-1]["values"]["PR383"], 12.34)
                ati_before = fake.ati_count
                time.sleep(3.3)
                self.assertEqual(
                    fake.ati_count, ati_before, "ATI interrupted active polling"
                )
                monitor.update_codes({"codes": ["PR064"]})
                deadline = time.monotonic() + 3
                while (
                    "PR064" not in monitor.snapshot()["samples"][-1]["values"]
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                self.assertEqual(
                    monitor.snapshot()["samples"][-1]["values"], {"PR064": 27.0}
                )
                self.assertEqual(opened.call_count, 1)
                monitor.update_codes({"codes": []})
                time.sleep(0.7)
                self.assertTrue(monitor.thread.is_alive())
                monitor.stop()
                monitor.thread.join(4)
                self.assertIsNotNone(monitor.connection.elm)
                count = len(fake.requests)
                time.sleep(3.1)
                self.assertEqual(len(fake.requests), count)  # idle: no ECU traffic
                self.assertEqual(opened.call_count, 1)
                self.assertFalse(monitor.thread.is_alive())
                self.assertTrue(
                    set(fake.requests) <= {"10C0", "2180", "22242C", "222001", "3E01"}
                )
        finally:
            monitor.stop()
            if monitor.thread:
                monitor.thread.join(4)
            monitor.connection.close()
            fake.close()
            if monitor.log_path:
                Path(monitor.log_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
