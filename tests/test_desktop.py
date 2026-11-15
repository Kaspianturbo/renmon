"""Native startup guards and direct monitor lifecycle without a GUI or car."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon import desktop
from renmon.features.desktop.lifecycle import DesktopSession
from renmon.features.ecu.profile import Profile
from renmon.features.monitoring.service import Monitor

ROOT = Path(__file__).resolve().parents[1]


class DesktopTests(unittest.TestCase):
    def test_missing_runtime_native_prompt_before_server(self):
        for answer in (6, 7):
            with (
                self.subTest(answer=answer),
                patch.object(desktop.sys, "platform", "win32"),
                patch.object(desktop, "has_webview2", return_value=False),
                patch.object(desktop, "windows_message", return_value=answer) as dialog,
                patch.object(desktop.webbrowser, "open") as browser,
                patch("renmon.features.desktop.lifecycle.DesktopSession") as server,
            ):
                self.assertEqual(desktop.main(), 1)
                server.assert_not_called()
                self.assertIn(desktop.WEBVIEW2_URL, dialog.call_args.args[1])
                self.assertEqual(browser.call_count, int(answer == 6))

    def test_registry_views_and_invalid_versions(self):
        registry = SimpleNamespace(
            HKEY_CURRENT_USER=1,
            HKEY_LOCAL_MACHINE=2,
            KEY_WOW64_32KEY=32,
            KEY_WOW64_64KEY=64,
            KEY_READ=256,
            OpenKey=MagicMock(),
            QueryValueEx=MagicMock(),
        )
        with patch.dict(sys.modules, {"winreg": registry}):
            registry.QueryValueEx.side_effect = [
                ("0.0.0.0", 1),
                ("", 1),
                OSError(),
                ("120.0.1.2", 1),
            ]
            self.assertTrue(desktop.has_webview2())
            self.assertEqual(registry.OpenKey.call_count, 4)
            registry.QueryValueEx.side_effect = OSError()
            self.assertFalse(desktop.has_webview2())

    def test_close_stops_demo_and_connection_without_socket(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "socket.socket.bind", side_effect=AssertionError("HTTP socket opened")
            ),
        ):
            monitor = Monitor(Profile.load(ROOT / "profiles/11075.json"), directory)
            backend = DesktopSession(monitor)
            monitor.start(dict(mode="demo", codes=["PR383"], interval=0.3))
            backend.close()
            backend.close()  # window.closed and finally may both run
            self.assertFalse(monitor.thread.is_alive())
            self.assertFalse(monitor.connection.worker.is_alive())
            self.assertFalse(backend._watchdog.is_alive())

    def test_webview_failure_closes_backend(self):
        fake = MagicMock()
        fake.start.side_effect = RuntimeError("renderer failed")
        with (
            patch.dict(sys.modules, {"webview": fake}),
            patch.object(desktop, "check_runtime", return_value=True),
            patch("renmon.features.desktop.lifecycle.DesktopSession") as server,
            patch.object(desktop, "show_error") as error,
        ):
            self.assertEqual(desktop.main(), 1)
            server.return_value.close.assert_called_once()
            error.assert_called_once()
            kwargs = fake.create_window.call_args.kwargs
            self.assertIn("html", kwargs)
            self.assertNotIn("url", kwargs)
            self.assertNotIn('src="/app.js"', kwargs["html"])
            self.assertFalse(fake.start.call_args.kwargs["http_server"])

    def test_portable_paths(self):
        with patch.object(desktop.sys, "frozen", True, create=True):
            with (
                patch.object(desktop.sys, "platform", "darwin"),
                patch.object(
                    desktop.sys,
                    "executable",
                    "/tmp/Portable/Renmon.app/Contents/MacOS/Renmon",
                ),
            ):
                self.assertEqual(
                    desktop.portable_root(), Path("/tmp/Portable").resolve()
                )
            with (
                patch.object(desktop.sys, "platform", "win32"),
                patch.object(desktop.sys, "executable", str(ROOT / "Renmon.exe")),
            ):
                self.assertEqual(desktop.portable_root(), ROOT)


if __name__ == "__main__":
    unittest.main()
