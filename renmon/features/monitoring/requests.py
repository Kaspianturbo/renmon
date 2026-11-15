"""Validate monitoring requests before starting workers or touching the adapter."""

import math
from dataclasses import dataclass

from .cadence import divisors

MAX_SIGNALS = 10
SESSIONS = ("", "10C0", "1003")


def selected_codes(value, *, allow_empty=False):
    minimum = 0 if allow_empty else 1
    if (
        not isinstance(value, list)
        or not minimum <= len(value) <= MAX_SIGNALS
        or not all(isinstance(code, str) for code in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"Оберіть від {minimum} до {MAX_SIGNALS} різних параметрів")
    return tuple(value)


def session_request(value):
    if value not in SESSIONS:
        raise ValueError("Недозволена сесія")
    return value


@dataclass(frozen=True)
class StartRequest:
    mode: str
    codes: tuple[str, ...]
    interval: float
    port: str
    session: str
    performance: bool
    divisors: dict

    @classmethod
    def parse(cls, config):
        mode = config.get("mode")
        if mode not in ("demo", "live"):
            raise ValueError("Невідомий режим")
        codes = selected_codes(config.get("codes"))
        raw_interval = config.get("interval", 1)
        if isinstance(raw_interval, bool):
            raise ValueError("Некоректний інтервал")
        interval = float(raw_interval)
        if not math.isfinite(interval) or not 0.1 <= interval <= 10:
            raise ValueError("Інтервал має бути від 0.1 до 10 секунд")
        port = config.get("port", "")
        if not isinstance(port, str):
            raise ValueError("Некоректний serial-порт")
        session = session_request(config.get("session", ""))
        performance = config.get("performance", False)
        if type(performance) is not bool:
            raise ValueError("Performance має бути boolean")
        return cls(
            mode,
            codes,
            interval,
            port,
            session,
            performance,
            divisors(config.get("divisors", {}), codes),
        )
