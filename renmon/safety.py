"""Fail-closed command policy, shared by CLI and browser monitor."""

import re


class SafetyError(ValueError):
    pass


SETUP = frozenset(
    (
        "ATI",
        "ATZ",
        "ATE0",
        "ATL0",
        "ATS0",
        "ATH0",
        "ATAL",
        "ATCAF1",
        "ATSP6",
        "ATFCSD300000",
        "ATFCSM1",
        "ATSTFF",
        "ATAT1",
    )
)
SESSIONS = frozenset(("1001", "10C0", "1003"))
KEEPALIVE = frozenset(("3E00", "3E01"))


def read_request(value):
    return isinstance(value, str) and re.fullmatch(r"22[0-9A-F]{4}", value) is not None


def can_id(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[0-9A-F]{3}", value)
        or int(value, 16) > 0x7EF
        or value == "7DF"
    ):
        raise SafetyError("Only physical 11-bit CAN addresses below 7F0 are supported")
    return value


def command(value, approved_multi=()):
    if not isinstance(value, str) or any(c in value for c in "\r\n\t\x00"):
        raise SafetyError("Control characters are forbidden")
    value = value.replace(" ", "").upper()
    if value in approved_multi and re.fullmatch(r"22(?:[0-9A-F]{4}){2,3}", value):
        return value
    if (
        value in SETUP
        or value in SESSIONS
        or value in KEEPALIVE
        or value == "2180"
        or read_request(value)
    ):
        return value
    for prefix in ("ATSH", "ATCRA", "ATFCSH"):
        if value.startswith(prefix):
            can_id(value[len(prefix) :])
            return value
    raise SafetyError("Command blocked by read-only policy")
