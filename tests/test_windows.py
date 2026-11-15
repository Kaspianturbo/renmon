"""Portable tests of Windows discovery and the COM monitoring path (no hardware)."""

import sys
import serial.tools.list_ports
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon.serial_ports import ports
from renmon.profile import Profile
from renmon.features.monitoring.service import Monitor

ROOT = Path(__file__).resolve().parents[1]


class MemorySerial:
    def __init__(self, port, **kwargs):
        self.port = port
        self.pending = b""
        self.commands = []
        self.closed = False

    def reset_input(self):
        self.pending = b""

    def write(self, data):
        command = data.decode().strip()
        self.commands.append(command)
        reply = {
            "ATI": "ELM327 v1.5",
            "2180": "618000000000000100000000000000000003",
            "22242C": "62 24 2C 04 D2",
        }.get(command, "OK")
        self.pending = (reply + "\r>").encode()

    def read(self, size):
        result, self.pending = self.pending[:size], self.pending[size:]
        return result

    def close(self):
        self.closed = True


class WindowsTests(unittest.TestCase):
    def test_port_discovery(self):
        devices = [
            "COM12",
            "COM2",
            "COM1",
            "COM2",
            "COM0",
            "COM3:",
            "COM1/evil",
            "/dev/cu.V-LINK",
            "/dev/tty.V-LINK",
        ]
        with patch(
            "serial.tools.list_ports.comports",
            return_value=[SimpleNamespace(device=p) for p in devices],
        ):
            with patch("renmon.features.connection.ports.sys.platform", "win32"):
                self.assertEqual(ports(), ["COM1", "COM2", "COM12"])
            with patch("renmon.features.connection.ports.sys.platform", "darwin"):
                self.assertEqual(ports(), ["/dev/cu.V-LINK"])

    def test_windows_manual_read_and_stop_releases_com(self):
        adapter = MemorySerial("COM12")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("renmon.features.connection.service.sys.platform", "win32"),
            patch(
                "serial.tools.list_ports.comports",
                return_value=[SimpleNamespace(device="COM12")],
            ),
            patch(
                "renmon.features.connection.service.SerialTransport",
                return_value=adapter,
            ) as opened,
            patch("renmon.features.connection.service.subprocess.run") as native,
            patch("renmon.features.monitoring.service.ROOT", Path(directory)),
        ):
            monitor = Monitor(
                Profile.load(ROOT / "profiles/11075.json"),
                profile_dir=ROOT / "profiles",
            )
            try:
                with self.assertRaises(ValueError):
                    monitor.select_adapter({"port": "COM99"})
                monitor.start(
                    dict(
                        mode="live",
                        port="COM12",
                        codes=["PR383"],
                        interval=0.3,
                        session="",
                    )
                )
                deadline = time.monotonic() + 4
                while (
                    len(monitor.snapshot()["samples"]) < 2
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                samples = monitor.snapshot()["samples"]
                self.assertGreaterEqual(len(samples), 2, monitor.error)
                self.assertEqual(samples[-1]["values"], {"PR383": 12.34})
                opened.assert_called_once_with("COM12", timeout=0.1, settle=0)
                native.assert_not_called()
                monitor.stop()
                monitor.thread.join(3)
                self.assertTrue(adapter.closed)
                self.assertFalse(monitor.thread.is_alive())
            finally:
                monitor.stop()
                if monitor.thread:
                    monitor.thread.join(3)
                monitor.connection.close()
            self.assertTrue(adapter.closed)


if __name__ == "__main__":
    unittest.main()
