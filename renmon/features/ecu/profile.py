"""Validated ECU profiles and signal decoding; no transport ownership."""

from __future__ import annotations

import itertools
import json
import logging
import math
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from renmon.safety import KEEPALIVE, SESSIONS, SafetyError, can_id, read_request

from .decode import DecodeError, apply_sign, compile_formula, evaluate, extract_bits


@dataclass
class Signal:
    code: str
    name: str
    kind: str
    label: str
    unit: str
    request: str
    positive: str
    formula: str
    sources: list[dict]
    label_uk: str = ""
    interpretations: dict[str, dict[str, str]] = field(default_factory=dict)
    _code = None

    def __post_init__(self):
        self._code = compile_formula(self.formula)

    @cached_property
    def demo_states(self):
        # Enumerate the small state input domain, so demo codes pass through the
        # same CLIP formula as real replies (e.g. ET824 raw 1 means STATUS2).
        if self.kind != "state" or sum(s["bits"] for s in self.sources) > 12:
            return []
        outputs = set()
        for inputs in itertools.product(*(range(1 << s["bits"]) for s in self.sources)):
            values = [apply_sign(v, s["type"]) for v, s in zip(inputs, self.sources)]
            value = float(evaluate(self._code, values))
            if value.is_integer() and str(int(value)) in self.interpretations:
                outputs.add(value)
        return sorted(outputs)

    def decode(self, payload: bytes) -> float:
        if not read_request(self.request) or not payload.startswith(
            bytes.fromhex("62" + self.request[2:])
        ):
            raise DecodeError("Response service or DID does not match request")
        values = [
            apply_sign(
                extract_bits(payload, s["start_byte"], s["start_bit"], s["bits"]),
                s["type"],
            )
            for s in self.sources
        ]
        try:
            value = float(evaluate(self._code, values))
            if not math.isfinite(value):
                raise ValueError("non-finite value")
            return value
        except (ArithmeticError, ValueError, TypeError, NameError) as exc:
            raise DecodeError(str(exc)) from exc


@dataclass
class Profile:
    ecu: str
    doc: str
    tx_id: str
    rx_id: str
    start_session: str
    keep_alive: str
    signals: list[Signal]
    did_lengths: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        can_id(raw["tx_id"])
        can_id(raw["rx_id"])
        if (
            raw.get("start_session", "10C0") not in SESSIONS
            or raw.get("keep_alive", "3E01") not in KEEPALIVE
        ):
            raise SafetyError("Unsupported session or keepalive in profile")
        excluded = [s for s in raw["signals"] if not read_request(s.get("request"))]
        if excluded:
            logging.getLogger(__name__).warning(
                "Excluded %d signals outside single-DID read policy", len(excluded)
            )
        known = {f for f in Signal.__dataclass_fields__ if not f.startswith("_")}
        signals = [
            Signal(**{k: v for k, v in s.items() if k in known})
            for s in raw["signals"]
            if read_request(s.get("request"))
        ]
        return cls(
            ecu=raw["ecu"],
            doc=raw.get("doc", ""),
            tx_id=raw["tx_id"],
            rx_id=raw["rx_id"],
            start_session=raw.get("start_session", "10C0"),
            keep_alive=raw.get("keep_alive", "3E01"),
            signals=signals,
            did_lengths={
                k: v
                for k, v in raw.get("did_lengths", {}).items()
                if read_request("22" + k) and type(v) is int and 0 < v <= 4090
            },
        )

    def by_code(self, codes: list[str]) -> list[Signal]:
        index = {s.code: s for s in self.signals}
        missing = [c for c in codes if c not in index]
        if missing:
            raise KeyError(f"unknown signals: {', '.join(missing)}")
        return [index[c] for c in codes]

    def search(self, needle: str) -> list[Signal]:
        needle = needle.upper()
        return [
            s
            for s in self.signals
            if needle in s.code.upper()
            or needle in s.label.upper()
            or needle in s.label_uk.upper()
        ]
