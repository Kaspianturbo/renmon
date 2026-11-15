"""Android boundaries tested without a JVM, phone or physical ECU."""

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from renmon.features.android.bluetooth import BluetoothTransport, address_from_target
from renmon.features.android.lifecycle import AndroidSession
from renmon.features.connection.service import Connection
from renmon.features.ecu.profile import Profile
from renmon.features.monitoring.service import Monitor

ROOT = Path(__file__).resolve().parents[1]


class AndroidTests(unittest.TestCase):
    def test_only_explicit_bluetooth_address(self):
        self.assertEqual(
            address_from_target("V-Link · 01:23:45:67:89:AB"), "01:23:45:67:89:AB"
        )
        for target in (
            "/dev/cu.test",
            "localhost:35000",
            "V-Link",
            "01:23:45:67:89:AB/evil",
        ):
            with self.assertRaises(ValueError):
                address_from_target(target)

    def test_transport_bytes_timeout_and_close(self):
        socket = MagicMock()
        incoming = socket.getInputStream.return_value
        incoming.available.side_effect = [2, 0, 0]
        incoming.read.side_effect = [65, 62]
        link = BluetoothTransport(socket, read_timeout=0)
        self.assertEqual(link.read(4), b"A>")
        self.assertEqual(link.read(), b"")
        link.write(b"ATI\r")
        socket.getOutputStream.return_value.write.assert_called_once_with(
            bytearray(b"ATI\r")
        )
        link.close()
        link.close()
        socket.close.assert_called_once()
        with self.assertRaises(OSError):
            link.write(b"ATI\r")
        with self.assertRaises(OSError):
            link.read()

    def test_connect_timeout_closes_socket(self):
        socket = MagicMock()
        closed = threading.Event()
        socket.close.side_effect = closed.set
        socket.connect.side_effect = lambda: closed.wait(1)
        with self.assertRaises(OSError):
            BluetoothTransport(socket, connect_timeout=0.01)
        self.assertTrue(closed.is_set())

    def test_failed_connect_closes_socket(self):
        socket = MagicMock()
        socket.connect.side_effect = RuntimeError("Java error")
        with self.assertRaises(OSError):
            BluetoothTransport(socket)
        socket.close.assert_called_once()

    def test_suspend_blocks_background_and_manual_open(self):
        factory = MagicMock(side_effect=AssertionError("adapter opened"))
        connection = Connection(transport_factory=factory)
        try:
            connection.suspend()
            connection.select("V-Link · 01:23:45:67:89:AB", auto_connect=True)
            with self.assertRaises(ValueError):
                connection.begin(connection.target)
            with self.assertRaises(OSError):
                connection._attempt()
            factory.assert_not_called()
        finally:
            connection.close()

    def test_overlapping_pause_cleanup_keeps_actions_blocked(self):
        monitor = MagicMock()
        monitor.thread = None
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        count = iter(range(2))

        def suspend():
            index = next(count)
            entered[index].set()
            release[index].wait(2)

        monitor.connection.suspend.side_effect = suspend
        session = AndroidSession(monitor)
        try:
            session.pause()
            self.assertTrue(entered[0].wait(1))
            session.resume()
            session.pause()
            self.assertTrue(entered[1].wait(1))
            release[0].set()
            self.assertFalse(session._cleanup.wait(0.05))
            with self.assertRaises(ValueError):
                session.ensure_open()
            release[1].set()
            self.assertTrue(session._cleanup.wait(1))
            session.resume()
            session.ensure_open()
            monitor.start.assert_not_called()
        finally:
            for event in release:
                event.set()
            session.close()

    def test_background_stops_demo_and_resume_needs_explicit_start(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = Monitor(Profile.load(ROOT / "profiles/11075.json"), directory)
            session = AndroidSession(monitor)
            try:
                monitor.start(dict(mode="demo", codes=["PR064"], interval=0.1))
                session.pause()
                self.assertTrue(session._cleanup.wait(2))
                self.assertFalse(monitor.thread.is_alive())
                self.assertFalse(monitor.connection.auto_connect)
                with self.assertRaises(ValueError):
                    session.ensure_open()
                session._last_seen = time.monotonic() - 30
                self.assertFalse(session.expire_if_needed())
                session.resume()
                session.ensure_open()
                self.assertFalse(monitor.thread.is_alive())
                monitor.start(dict(mode="demo", codes=["PR064"], interval=0.1))
            finally:
                session.close()
            self.assertFalse(monitor.connection.worker.is_alive())
