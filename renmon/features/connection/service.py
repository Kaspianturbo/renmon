"""One owner for the ELM link; idle traffic is adapter-only ATI."""

import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from renmon.elm import Elm, ElmError
from renmon.transport import SerialTransport

log = logging.getLogger(__name__)


class Connection:
    def __init__(self, transport_factory=None):
        self.transport_factory = transport_factory
        self.suspended = threading.Event()
        self.lock = threading.RLock()
        self.target = ""
        self.auto_connect = False
        self.active = False
        self.elm = None
        self.generation = 0
        self.status = "disabled"
        self.error = ""
        self.misses = 0
        self.attempts = 0
        self.bluetooth = ""
        self.last_activity = 0.0
        self.closed = threading.Event()
        self.wake = threading.Event()
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def select(self, target, auto_connect=False):
        with self.lock:
            if self.closed.is_set():
                raise ValueError("Підключення вже закрито")
            if target != self.target or auto_connect != self.auto_connect:
                self._drop()
                self.target = target
                self.auto_connect = auto_connect
                self.status = (
                    ("waiting" if auto_connect else "idle") if target else "disabled"
                )
                self.error = ""
                self.misses = 0
                self.attempts = 0
                log.info(
                    "Adapter selected: port=%s auto_connect=%s", target, auto_connect
                )
        self.wake.set()

    def _drop(self):
        if self.elm:
            try:
                self.elm.io.close()  # do not reset the adapter on Stop
            except OSError:
                pass
        self.elm = None

    def _loop(self):
        while not self.closed.is_set():
            began = time.monotonic()
            with self.lock:
                if self.closed.is_set():
                    break
                if (
                    not self.suspended.is_set()
                    and self.auto_connect
                    and self.target
                    and (not self.active or self.status != "connected")
                    and not (
                        self.status == "connected"
                        and time.monotonic() - self.last_activity < 3
                    )
                ):
                    try:
                        self._attempt()
                    except Exception as exc:
                        log.warning(
                            "Autoconnect attempt %d failed: %s", self.attempts, exc
                        )
                        self.misses += 1
                        if self.misses >= 3:
                            self._drop()
                            self.misses = 0
                        self.status, self.error = "waiting", str(exc)
            self.wake.wait(max(0.1, 3 - (time.monotonic() - began)))
            self.wake.clear()

    def _attempt(self):
        """One adapter-only connection attempt; caller holds the serial lock."""
        if self.suspended.is_set() or self.closed.is_set():
            raise OSError("Підключення призупинено")
        self.attempts += 1
        was_connected = self.status == "connected"
        self.status = "connecting"
        if self.elm is None:
            log.info("Opening adapter: port=%s attempt=%d", self.target, self.attempts)
        helper = Path(__file__).resolve().parents[2] / "native" / "bluetooth-connect"
        if (
            self.elm is None
            and self.auto_connect
            and sys.platform == "darwin"
            and helper.is_file()
        ):
            try:
                result = subprocess.run(
                    [str(helper), self.target],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                native = json.loads(result.stdout)
                self.bluetooth = native.get("state", "")
                log.info("macOS Bluetooth helper: %s", native)
            except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
                self.bluetooth = "unknown"
                log.warning(
                    "macOS Bluetooth helper failed; trying serial port: %s", exc
                )
            # ACL state is advisory: opening the selected SPP port establishes
            # the actual RFCOMM link even if the helper could not connect it.
        if self.elm is None:
            self.status = "connecting"
            self.elm = Elm(
                (self.transport_factory or SerialTransport)(
                    self.target, timeout=0.1, settle=0
                ),
                timeout=5,
            )
            self.generation += 1
        if self.suspended.is_set() or self.closed.is_set():
            self._drop()
            raise OSError("Підключення призупинено")
        reply = self.elm.send("ATI", timeout=5)
        if not reply.strip() or "?" in reply:
            raise ElmError("ATI: adapter identification missing")
        if not was_connected:
            log.info(
                "Adapter connected: port=%s identification=%r",
                self.target,
                reply.strip(),
            )
        self.status, self.error = "connected", ""
        self.misses = 0
        self.last_activity = time.monotonic()

    def begin(self, target):
        """Acquire a live link; manual mode tries once and fails explicitly."""
        self.select(target, self.auto_connect)
        with self.lock:
            if self.suspended.is_set():
                raise ValueError("Підключення призупинено")
            if not target:
                raise ValueError("Оберіть serial-порт")
            self.active = True
            if not self.auto_connect and self.status != "connected":
                try:
                    self._attempt()
                except Exception:
                    self._drop()
                    self.status = "idle"
                    raise

    def finish(self):
        with self.lock:
            self.active = False
            if not self.auto_connect:
                self._drop()
                self.status = "idle" if self.target else "disabled"
        self.wake.set()

    def suspend(self):
        """Gate background work immediately; release an in-flight socket if possible."""
        self.suspended.set()
        self.auto_connect = False
        self.wake.set()
        # Android socket close is thread-safe and interrupts blocking I/O.
        elm = self.elm
        if elm is not None and hasattr(elm.io, "interrupt"):
            elm.io.interrupt()
        with self.lock:
            self._drop()
            self.active = False
            self.status = "idle" if self.target else "disabled"

    def resume(self):
        # Never resume polling or autoconnect implicitly after backgrounding.
        self.suspended.clear()

    def snapshot(self):
        # Status reads must not wait for serial I/O.
        return dict(
            port=self.target,
            status=self.status,
            error=self.error,
            auto_connect=self.auto_connect,
            attempts=self.attempts,
        )

    def request_close(self):
        """Prevent further background attempts without waiting for serial I/O."""
        self.closed.set()
        self.wake.set()

    def close(self):
        self.request_close()
        self.worker.join(8)
        with self.lock:
            self._drop()
