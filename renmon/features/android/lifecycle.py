"""Foreground-only monitoring with an explicit restart after backgrounding."""

import threading

from ..desktop.lifecycle import DesktopSession


class AndroidSession(DesktopSession):
    def __init__(self, monitor, **kwargs):
        self.operation_lock = threading.RLock()
        self._paused = False
        self._cleanup_count = 0
        self._cleanup = threading.Event()
        self._cleanup.set()
        super().__init__(monitor, **kwargs)

    def ensure_open(self):
        super().ensure_open()
        if self._paused or not self._cleanup.is_set():
            raise ValueError(
                "Читання призупинено: поверніться до Renmon і натисніть «Почати»"
            )

    def expire_if_needed(self):
        with self._lock:
            if self._paused:
                return False
        return super().expire_if_needed()

    def pause(self, *_args):
        with self._lock:
            if self._closed.is_set() or self._paused:
                return
            self._paused = True
            self._cleanup_count += 1
            self._cleanup.clear()
        self.monitor.connection.suspended.set()
        self.monitor.stop()

        def stop_link():
            try:
                self.monitor.connection.suspend()
                with self.operation_lock:
                    self.monitor.stop()
                    if self.monitor.thread is not None:
                        self.monitor.thread.join(15)
            finally:
                with self._lock:
                    self._cleanup_count -= 1
                    if not self._cleanup_count:
                        if not self._paused and not self._closed.is_set():
                            self.monitor.connection.resume()
                        self._cleanup.set()

        threading.Thread(target=stop_link, name="Android pause", daemon=True).start()

    def resume(self, *_args):
        with self._lock:
            if self._closed.is_set():
                return
            self._paused = False
            self._last_seen = self._clock()

        with self._lock:
            if self._cleanup.is_set():
                self.monitor.connection.resume()
