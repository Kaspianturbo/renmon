"""The native bridge has no sockets, arbitrary commands or UI-supplied file paths."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from renmon.features.desktop.assets import document
from renmon.features.desktop.bridge import DesktopAPI
from renmon.features.desktop.lifecycle import DesktopSession
from renmon.features.ecu.profile import Profile
from renmon.features.monitoring.service import Monitor

ROOT = Path(__file__).resolve().parents[1]


class BridgeTests(unittest.TestCase):
    def test_native_actions_demo_export_and_close(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("socket.socket.bind", side_effect=AssertionError("No sockets")),
        ):
            monitor = Monitor(
                Profile.load(ROOT / "profiles/11075.json"),
                directory,
                port_provider=lambda: ["COM12"],
            )
            session = DesktopSession(monitor)
            save = Mock(return_value=True)
            api = DesktopAPI(session, save)
            try:
                self.assertEqual(api.call("ports")["result"], {"ports": ["COM12"]})
                self.assertEqual(api.call("catalog")["result"]["ecu"], "11075")
                self.assertTrue(
                    api.call(
                        "start", {"mode": "demo", "codes": ["PR383"], "interval": 0.1}
                    )["ok"]
                )
                deadline = time.monotonic() + 2
                while not monitor.snapshot()["samples"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(api.call("state")["result"]["samples"])
                self.assertTrue(api.call("export")["result"]["saved"])
                self.assertIn(b"PR383", save.call_args.args[0])
                self.assertTrue(api.call("signals", {"codes": []})["ok"])
                self.assertTrue(api.call("stop")["ok"])
                for action, data in [
                    ("raw", {"command": "1101"}),
                    ("__dict__", {}),
                    ("start", []),
                    ("start", {"interval": float("nan")}),
                    ("start", {"x": "a" * 8193}),
                    ("adapter", {"port": "COM99"}),
                ]:
                    self.assertFalse(api.call(action, data)["ok"])
                save.return_value = False
                self.assertFalse(api.call("export")["result"]["saved"])
            finally:
                session.close()
            self.assertFalse(
                api.call("start", {"mode": "demo", "codes": ["PR383"]})["ok"]
            )
            self.assertFalse(monitor.connection.worker.is_alive())

    def test_ui_lease_closes_idle_autoconnect_and_cannot_resume(self):
        # No monitoring worker is running: the watchdog must still stop the link.
        now = [100.0]
        monitor = Mock()
        session = DesktopSession(monitor, clock=lambda: now[0])
        api = DesktopAPI(session, Mock())
        try:
            now[0] += 10
            session.heartbeat()
            now[0] += 10
            self.assertFalse(session.expire_if_needed())
            now[0] += 6
            self.assertTrue(session.expire_if_needed())
            monitor.close.assert_called_once()
            self.assertFalse(api.call("state")["ok"])
            self.assertFalse(
                api.call("adapter", {"port": "COM12", "auto_connect": True})["ok"]
            )
            monitor.select_adapter.assert_not_called()
        finally:
            session.close()
        monitor.close.assert_called_once()

    def test_expiry_closes_real_idle_connection_and_prevents_reconnect(self):
        from test_windows import MemorySerial

        adapter = MemorySerial("COM12")
        now = [100.0]
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("renmon.features.connection.service.sys.platform", "win32"),
            patch(
                "renmon.features.connection.service.SerialTransport",
                return_value=adapter,
            ) as opened,
        ):
            monitor = Monitor(
                Profile.load(ROOT / "profiles/11075.json"),
                directory,
                port_provider=lambda: ["COM12"],
            )
            session = DesktopSession(monitor, clock=lambda: now[0])
            api = DesktopAPI(session, Mock())
            try:
                self.assertTrue(
                    api.call("adapter", {"port": "COM12", "auto_connect": True})["ok"]
                )
                deadline = time.monotonic() + 2
                while (
                    monitor.connection.status != "connected"
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                self.assertEqual(monitor.connection.status, "connected")
                self.assertIsNone(monitor.thread)
                now[0] += 16
                self.assertTrue(session.expire_if_needed())
                self.assertTrue(adapter.closed)
                self.assertIsNone(monitor.connection.elm)
                self.assertFalse(monitor.connection.worker.is_alive())
                self.assertFalse(
                    api.call("adapter", {"port": "COM12", "auto_connect": True})["ok"]
                )
                opened.assert_called_once()
                self.assertEqual(adapter.commands, ["ATI"])
            finally:
                session.close()

    def test_watchdog_runs_without_ui_calls(self):
        monitor = Mock()
        session = DesktopSession(monitor, timeout=0.01)
        try:
            self.assertTrue(session._finished.wait(2))
            monitor.close.assert_called_once()
        finally:
            session.close()

    def test_native_save_supports_mac_string_and_windows_sequence(self):
        from renmon.features.desktop.dialogs import save_csv
        import sys

        window = Mock()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(sys.modules, {"webview": Mock()}),
        ):
            target = Path(directory) / "export.csv"
            for selection in (str(target), (str(target),), [str(target)]):
                window.create_file_dialog.return_value = selection
                self.assertTrue(save_csv(window, b"test"))
                self.assertEqual(target.read_bytes(), b"test")
            window.create_file_dialog.return_value = None
            self.assertFalse(save_csv(window, b"changed"))
            self.assertEqual(target.read_bytes(), b"test")

    def test_self_contained_document_has_no_navigation_or_external_assets(self):
        html = document()
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn("href=", html)
        self.assertNotIn("src=", html)
        self.assertNotIn("fetch(", html)
        self.assertIn("pywebviewready", html)
        self.assertIn("export-csv", html)


if __name__ == "__main__":
    unittest.main()
