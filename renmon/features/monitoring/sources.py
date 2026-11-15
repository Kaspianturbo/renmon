"""Read one cycle; keep protocol setup out of the session coordinator."""

import time
from dataclasses import dataclass

from .demo import demo_value
from .performance import Performance
from .poller import Poller


@dataclass
class Reading:
    values: dict
    errors: dict
    elapsed: float
    requests: int


class DemoReader:
    def __init__(self):
        self.started = time.monotonic()

    def cycle(self, signals, stop):
        began = time.monotonic()
        values = {
            signal.code: demo_value(signal, began - self.started) for signal in signals
        }
        return Reading(values, {}, time.monotonic() - began, 0)


class LiveReader:
    def __init__(self, connection, profile, catalog, session, performance=False):
        self.connection = connection
        self.profile = profile
        self.catalog = catalog
        self.session = session
        self.enabled = performance
        self.performance = Performance(profile.did_lengths, performance)
        self.generation = -1
        self.last_keep = 0.0

    def cycle(self, signals, stop):
        connection = self.connection
        if stop.is_set() or connection.status != "connected":
            return None
        with connection.lock:
            elm = connection.elm
            if stop.is_set() or elm is None or connection.status != "connected":
                return None
            if self.generation != connection.generation:
                elm.timeout = 5
                elm.connect(self.profile.tx_id, self.profile.rx_id, stop=stop)
                if stop.is_set():
                    return None
                if self.session:
                    elm.start_session(self.session)
                if stop.is_set():
                    return None
                self.catalog.verify(elm, expected=self.profile.ecu)
                self.performance = Performance(self.profile.did_lengths, self.enabled)
                self.generation = connection.generation
                self.last_keep = time.monotonic()
            if stop.is_set():
                return None
            if self.session and time.monotonic() - self.last_keep > 2:
                elm.keep_alive(self.profile.keep_alive)
                self.last_keep = time.monotonic()
            if not signals:
                return Reading({}, {}, 0.0, 0)
            values, errors, elapsed = Poller(elm, signals, self.performance).cycle(stop)
            if values:
                connection.last_activity = time.monotonic()
            return Reading(values, errors, elapsed, self.performance.requests)
