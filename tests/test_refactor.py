"""Regression coverage for feature boundaries and lifecycle races."""

import ast
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from renmon.clip.formula import to_python
from renmon.features.ecu.profile import Profile
from renmon.features.monitoring.requests import StartRequest, selected_codes
from renmon.features.monitoring.service import Monitor
from renmon.transport import TcpTransport

ROOT = Path(__file__).resolve().parents[1]


class RefactorTests(unittest.TestCase):
    def test_c_formula_precedence_and_numeric_boolean(self):
        for source, expected in [
            ("2 || 4", 1),
            ("2 && 4", 1),
            ("4 & 1 == 0", 0),
            ("3 < 2 < 1", 1),
            ("8 >> 1 + 1", 2),
            ("1 ? 2 : 3 ? 4 : 5", 2),
            ("(3001-2730)/10", 27.1),
        ]:
            with self.subTest(source=source):
                self.assertEqual(
                    eval(to_python(source, []), {"__builtins__": {}}), expected
                )

    def test_request_validation_is_atomic_and_copies_input(self):
        for codes in ([{}], ["PR064", "PR064"], "PR064", [None]):
            with self.subTest(codes=codes), self.assertRaises(ValueError):
                selected_codes(codes)
        for value in (float("nan"), float("inf"), True, 0, 11):
            with self.subTest(value=value), self.assertRaises(ValueError):
                StartRequest.parse(
                    {"mode": "demo", "codes": ["PR064"], "interval": value}
                )
        codes = ["PR064"]
        request = StartRequest.parse({"mode": "demo", "codes": codes})
        codes.clear()
        self.assertEqual(request.codes, ("PR064",))

    def test_detect_does_not_block_state_and_stop_cancels_commit(self):
        connection = Mock()
        connection.lock = threading.RLock()
        connection.status = "connected"
        connection.snapshot.return_value = {}
        entered, release = threading.Event(), threading.Event()
        connection.elm.connect.side_effect = lambda *a, **k: (
            entered.set(),
            release.wait(3),
        )
        mon = Monitor(Profile.load(ROOT / "profiles/11075.json"), connection=connection)
        errors = []

        def detect():
            try:
                mon.detect({})
            except ValueError as error:
                errors.append(str(error))

        worker = threading.Thread(target=detect)
        try:
            worker.start()
            self.assertTrue(entered.wait(2))
            # This read would deadlock under the former serial/state lock nesting.
            done = threading.Event()
            reader = threading.Thread(target=lambda: (mon.snapshot(), done.set()))
            reader.start()
            self.assertTrue(done.wait(0.5))
            reader.join(1)
            with self.assertRaises(ValueError):
                mon.change_profile({"ecu": "11046"})
            with self.assertRaises(ValueError):
                mon.update_codes({"codes": ["PR064"]})
            mon.stop()
        finally:
            release.set()
            worker.join(3)
            mon.close()
        self.assertTrue(errors)
        connection.elm.request.assert_not_called()
        self.assertEqual(mon.profile.ecu, "11075")
        self.assertIsNone(mon.operation)

    def test_demo_disconnects_adapter_without_ui(self):
        connection = Mock()
        with tempfile.TemporaryDirectory() as directory:
            mon = Monitor(
                Profile.load(ROOT / "profiles/11075.json"),
                log_dir=directory,
                connection=connection,
            )
            try:
                mon.start({"mode": "demo", "codes": ["PR064"], "interval": 0.1})
                mon.stop()
                mon.thread.join(2)
                connection.select.assert_called_once_with("")
            finally:
                mon.close()

    def test_tcp_reset_preserves_timeout_and_eof_fails(self):
        sock = Mock()
        sock.gettimeout.return_value = 0.25
        sock.recv.side_effect = socket.timeout
        with patch("socket.create_connection", return_value=sock):
            link = TcpTransport("localhost", 1234, timeout=0.25)
            link.reset_input()
            sock.settimeout.assert_called_with(0.25)
            sock.recv.side_effect = None
            sock.recv.return_value = b""
            with self.assertRaises(ConnectionError):
                link.read()
            link.close()

    def test_features_do_not_import_delivery_layers(self):
        for path in (ROOT / "renmon/features").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn(
                        node.module,
                        ("renmon.web", "renmon.desktop", "renmon.cli"),
                        str(path),
                    )


if __name__ == "__main__":
    unittest.main()
