"""Decode selected signals after grouped diagnostic reads."""

import time

from renmon.elm import Elm, ElmError

from ..ecu.decode import DecodeError
from ..ecu.profile import Signal


class Poller:
    """Reads a set of signals, one request per distinct data identifier.

    Signals sharing a request are decoded from a single reply, which is the
    cheap half of the speedup over polling each parameter separately.
    """

    def __init__(self, elm: Elm, signals: list[Signal], performance=None):
        self.elm = elm
        self.performance = performance
        self.signals = signals
        self.groups: dict[str, list[Signal]] = {}
        for signal in signals:
            self.groups.setdefault(signal.request, []).append(signal)

    @property
    def requests_per_cycle(self) -> int:
        return len(self.groups)

    def cycle(self, stop=None) -> tuple[dict[str, float], dict[str, str], float]:
        """Return (values, errors, elapsed seconds)."""

        values: dict[str, float] = {}
        errors: dict[str, str] = {}
        started = time.monotonic()

        if self.performance is not None:
            payloads, request_errors = self.performance.read(
                self.elm, list(self.groups), stop
            )
        for request, signals in self.groups.items():
            if stop is not None and stop.is_set():
                break
            try:
                if self.performance is None:
                    payload = self.elm.request(request)
                else:
                    if request not in payloads:
                        if request in request_errors:
                            raise ElmError(request_errors[request])
                        continue
                    payload = payloads[request]
            except ElmError as exc:
                for signal in signals:
                    errors[signal.code] = str(exc)
                continue
            for signal in signals:
                try:
                    values[signal.code] = signal.decode(payload)
                except DecodeError as exc:
                    errors[signal.code] = str(exc)

        return values, errors, time.monotonic() - started
