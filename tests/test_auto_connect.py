"""Autoconnect is opt-in; manual reads never create idle adapter traffic."""

import time
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_windows import MemorySerial

from renmon.features.connection.service import Connection


class AutoConnectTests(unittest.TestCase):
    def test_port_selection_and_empty_auto_selection_do_not_open_port(self):
        with patch("renmon.features.connection.service.SerialTransport") as opened:
            connection = Connection()
            try:
                connection.select("COM12")
                # Let the background worker cross a complete retry interval.
                time.sleep(3.2)
                opened.assert_not_called()
                self.assertFalse(connection.snapshot()["auto_connect"])
                connection.select("", auto_connect=True)
                time.sleep(0.1)
                opened.assert_not_called()
            finally:
                connection.close()

    def test_enable_connects_disable_closes_and_stops_retry(self):
        adapter = MemorySerial("COM12")
        with (
            patch("renmon.features.connection.service.sys.platform", "win32"),
            patch(
                "renmon.features.connection.service.SerialTransport",
                return_value=adapter,
            ) as opened,
        ):
            connection = Connection()
            try:
                connection.select("COM12", auto_connect=True)
                deadline = time.monotonic() + 2
                while connection.status != "connected" and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(connection.status, "connected")
                self.assertEqual(adapter.commands, ["ATI"])
                connection.select("COM12", auto_connect=False)
                self.assertTrue(adapter.closed)
                time.sleep(3.2)
                opened.assert_called_once()
                self.assertEqual(adapter.commands, ["ATI"])
                self.assertEqual(connection.status, "idle")
            finally:
                connection.close()

    def test_native_failure_does_not_block_serial_or_idle_keepalive(self):
        for result in [
            SimpleNamespace(stdout='{"state":"waiting","detail":"not connected"}'),
            subprocess.TimeoutExpired("helper", 2),
            SimpleNamespace(stdout="invalid JSON"),
        ]:
            adapter = MemorySerial("/dev/cu.V-LINK")
            with (
                patch("renmon.features.connection.service.sys.platform", "darwin"),
                patch(
                    "renmon.features.connection.service.Path.is_file", return_value=True
                ),
                patch("renmon.features.connection.service.subprocess.run") as helper,
            ):
                if isinstance(result, Exception):
                    helper.side_effect = result
                else:
                    helper.return_value = result
                connection = Connection(transport_factory=lambda *a, **kw: adapter)
                try:
                    connection.select("/dev/cu.V-LINK", auto_connect=True)
                    deadline = time.monotonic() + 2
                    while (
                        connection.status != "connected" and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    self.assertEqual(connection.status, "connected", connection.error)
                    self.assertEqual(adapter.commands, ["ATI"])
                    with connection.lock:
                        connection.last_activity = 0
                    connection.wake.set()
                    deadline = time.monotonic() + 2
                    while len(adapter.commands) < 2 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertEqual(adapter.commands, ["ATI", "ATI"])
                    helper.assert_called_once()
                finally:
                    connection.close()

    def test_manual_failure_only_attempts_once(self):
        with patch(
            "renmon.features.connection.service.SerialTransport",
            side_effect=OSError("unavailable"),
        ) as opened:
            connection = Connection()
            try:
                connection.select("COM12")
                with self.assertRaises(OSError):
                    connection.begin("COM12")
                connection.finish()
                time.sleep(0.1)
                opened.assert_called_once_with("COM12", timeout=0.1, settle=0)
                self.assertIsNone(connection.elm)
            finally:
                connection.close()
