"""One window owns one monitor. A lost UI lease permanently closes that session."""

import threading
import time


class DesktopSession:
    def __init__(self, monitor, timeout=15.0, clock=time.monotonic):
        self.monitor = monitor
        self._timeout = timeout
        self._clock = clock
        self._last_seen = clock()
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._finished = threading.Event()
        self._reason = ""
        self._watchdog = threading.Thread(
            target=self._watch, name="Renmon UI watchdog", daemon=True
        )
        self._watchdog.start()

    def ensure_open(self):
        with self._lock:
            if self._closed.is_set():
                raise ValueError(self._reason or "Застосунок закривається")

    def heartbeat(self):
        with self._lock:
            if self._closed.is_set():
                raise ValueError(self._reason or "Застосунок закривається")
            self._last_seen = self._clock()
        self.monitor.touch()

    def expire_if_needed(self):
        with self._lock:
            if (
                self._closed.is_set()
                or self._clock() - self._last_seen <= self._timeout
            ):
                return False
            # Claim shutdown atomically with the lease check: a late heartbeat
            # cannot revive a session whose serial cleanup has already begun.
            self._reason = "Зв’язок з інтерфейсом втрачено. Читання й автопідключення завершені. Перезапустіть Renmon."
            self._closed.set()
        self._finish_close(True)
        return True

    def _watch(self):
        while not self._closed.wait(0.5):
            if self.expire_if_needed():
                break

    def close(self, reason=""):
        with self._lock:
            owner = not self._closed.is_set()
            if owner:
                self._reason = reason
                self._closed.set()
        self._finish_close(owner)

    def _finish_close(self, owner):
        if owner:
            try:
                self.monitor.close()
            finally:
                self._finished.set()
        else:
            self._finished.wait()
        if threading.current_thread() is not self._watchdog:
            self._watchdog.join()
