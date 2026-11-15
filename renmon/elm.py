"""ELM327 driver, scoped to what reading data identifiers needs.

Deliberately uses the adapter's own ISO-TP handling (``AT CAF1``) instead of
assembling frames by hand: for plain ``22 xx xx`` reads it is both simpler and
less adapter specific. Flow control is still pinned down explicitly, because
clones tend to get it wrong when left on defaults.
"""

from __future__ import annotations

import logging
import re
import time

from .safety import SafetyError, can_id, read_request
from .safety import command as safe_command
from .transport import Transport

log = logging.getLogger(__name__)

PROMPT = b">"
_HEX_LINE = re.compile(r"^[0-9A-F\s]+$")
# multiframe replies come back as "0:62 24 A9 ...", "1:..." with CAF1
_FRAME_INDEX = re.compile(r"^[0-9A-F]:")

BAUD_RATES = (38400, 115200, 230400, 500000, 1000000, 2000000)


class ElmError(RuntimeError):
    pass


class NegativeResponse(ElmError):
    """The ECU answered 7F <service> <code>."""

    CODES = {
        0x11: "service not supported",
        0x12: "sub function not supported",
        0x13: "wrong message length",
        0x22: "conditions not correct",
        0x31: "request out of range",
        0x33: "security access denied",
        0x78: "response pending",
    }

    def __init__(self, service: int, code: int):
        self.service = service
        self.code = code
        super().__init__(
            f"negative response to {service:02X}: "
            f"{self.CODES.get(code, 'unknown')} (0x{code:02X})"
        )


class Elm:
    def __init__(self, transport: Transport, timeout: float = 5.0):
        self.io = transport
        self.timeout = timeout
        self._buffer = ""
        self._approved_multi = set()
        self.last_exchange = None

    # -- raw exchange ----------------------------------------------------

    def _read_until_prompt(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        chunks: list[str] = []
        while time.monotonic() < deadline:
            byte = self.io.read(1)
            if not byte:
                continue
            char = byte.decode("ascii", "ignore")
            if char == ">":
                return "".join(chunks)
            chunks.append(char)
        raise ElmError(f"timeout after {timeout:.1f}s, got {''.join(chunks)!r}")

    def send(self, command: str, timeout: float | None = None) -> str:
        command = safe_command(command, self._approved_multi)
        self.last_exchange = (command, "")
        self.io.reset_input()
        self.io.write((command + "\r").encode("ascii"))
        try:
            raw = self._read_until_prompt(timeout or self.timeout)
        except ElmError as exc:
            raise ElmError(f"{command}: {exc}") from exc
        self.last_exchange = (command, raw)
        log.debug("%s -> %s", command, raw.strip().replace("\r", " "))
        return raw

    def at(self, command: str) -> str:
        reply = self.send(command)
        cleaned = " ".join(
            line.strip()
            for line in reply.replace("\r", "\n").splitlines()
            if line.strip() and line.strip() != command
        )
        if "?" in cleaned:
            raise ElmError(f"adapter rejected {command!r}")
        return cleaned

    # -- setup -----------------------------------------------------------

    def probe(self, baud_rates=BAUD_RATES, attempts: int = 3) -> int:
        """Find the adapter's baud rate.

        Repeats the sweep: a bluetooth link often needs a few seconds before
        the first byte actually goes anywhere, and one pass can be too early.
        """

        if not hasattr(self.io, "baudrate"):
            self.send("ATI")  # never repeat the adapter's previous command
            return 0

        for attempt in range(attempts):
            for rate in baud_rates:
                self.io.baudrate = rate
                self.io.reset_input()
                try:
                    self.io.write(b"ATI\r")
                    self._read_until_prompt(1.0)
                except ElmError:
                    continue
                log.info("adapter responds at %d baud", rate)
                return rate
            if attempt + 1 < attempts:
                log.info("no answer yet, waiting for the link")
                time.sleep(2.0)
        raise ElmError("adapter is not responding at any baud rate")

    def identify(self) -> str:
        return self.at("AT I")

    def wait_ready(self, stop, attempts=3):
        """Wait for Bluetooth using adapter-only ATI, never repeat ECU requests."""
        last = None
        for attempt in range(attempts):
            if stop.is_set():
                raise ElmError("Підключення скасовано")
            try:
                reply = self.identify()
                if reply.strip():
                    return reply
                raise ElmError("ATI: empty adapter identification")
            except ElmError as exc:
                last = exc
                if attempt + 1 < attempts and stop.wait(1):
                    raise ElmError("Підключення скасовано") from exc
        raise ElmError(
            f"ELM не відповів після {attempts} спроб перевірки Bluetooth: {last}"
        )

    def connect(self, tx_id: str, rx_id: str, stop=None) -> None:
        """Bring up ISO-TP over 11 bit CAN at 500 kbit, addressed to one ECU."""

        can_id(tx_id)
        can_id(rx_id)
        if stop is not None and stop.is_set():
            return
        self.at("AT Z")
        if stop is not None:
            if stop.wait(0.5):
                return
        else:
            time.sleep(0.5)
        self.io.reset_input()
        for command in (
            "AT E0",  # no echo
            "AT L0",  # no line feeds
            "AT S0",  # no spaces
            "AT H0",  # no headers in the reply
            "AT AL",  # allow long messages
            "AT CAF1",  # let the adapter do ISO-TP
            "AT SP 6",  # ISO 15765, 11 bit, 500 kbit
            f"AT SH {tx_id}",
            f"AT CRA {rx_id}",
            f"AT FC SH {tx_id}",
            "AT FC SD 30 00 00",
            "AT FC SM 1",
            "AT ST FF",  # max wait before giving up on a reply
            "AT AT 1",  # adaptive timing
        ):
            if stop is not None and stop.is_set():
                return
            self.at(command)

    # -- requests --------------------------------------------------------

    def request(self, payload: str, timeout: float | None = None) -> bytes:
        """Send a service request, return the assembled reply bytes."""

        raw = self.send(payload.replace(" ", "").upper(), timeout)
        data = self._parse(raw)

        if len(data) >= 3 and data[0] == 0x7F:
            if data[2] == 0x78:  # response pending, the ECU asks for more time
                raw = self._read_until_prompt(timeout or self.timeout)
                data = self._parse(raw)
                if not (len(data) >= 3 and data[0] == 0x7F):
                    return data
            raise NegativeResponse(data[1], data[2])
        return data

    def request_many(self, requests):
        if (
            not 2 <= len(requests) <= 3
            or len(set(requests)) != len(requests)
            or not all(read_request(r) for r in requests)
        ):
            raise SafetyError("Only 2–3 distinct single-DID reads may be combined")
        command = "22" + "".join(r[2:] for r in requests)
        self._approved_multi.add(command)
        try:
            return self.request(command)
        finally:
            self._approved_multi.discard(command)

    def _parse(self, raw: str) -> bytes:
        lines = [
            line.strip()
            for line in raw.replace("\r", "\n").splitlines()
            if line.strip()
        ]
        payload = ""
        declared_length = None
        indexed = False
        for line in lines:
            upper = line.upper()
            if upper in ("SEARCHING...", "OK"):
                continue
            for marker in (
                "NO DATA",
                "CAN ERROR",
                "BUS INIT",
                "UNABLE TO CONNECT",
                "BUFFER FULL",
                "STOPPED",
                "ERROR",
            ):
                if marker in upper:
                    raise ElmError(upper)
            if re.fullmatch(r"[0-9A-F]{3}", upper) and not payload:
                declared_length = int(upper, 16)
                continue
            if _FRAME_INDEX.match(upper):
                indexed = True
                upper = upper.split(":", 1)[1]
            upper = upper.replace(" ", "")
            if not _HEX_LINE.match(upper) or len(upper) % 2:
                continue
            payload += upper

        if not payload:
            raise ElmError(f"no usable data in {raw.strip()!r}")

        data = bytes.fromhex(payload)
        # CAF1 indexed replies declare the ISO-TP payload size separately.
        # Some adapters include the last CAN frame's padding. Only strip it
        # when the declared length and a complete final frame account for it.
        if indexed and declared_length is not None:
            padded_length = 6 + ((max(0, declared_length - 6) + 6) // 7) * 7
            if declared_length < 7 or len(data) not in (declared_length, padded_length):
                raise ElmError("ELM multiframe length does not match declared length")
            data = data[:declared_length]
        # with AT AL the adapter may prefix the ISO-TP length, drop it when the
        # remainder matches exactly
        if (
            len(data) > 1
            and data[0] == len(data) - 1
            and data[1] in (0x61, 0x62, 0x50, 0x7E, 0x7F)
        ):
            data = data[1:]
        return data

    def raw(
        self, payload: str, timeout: float | None = None
    ) -> tuple[str, bytes | None, str]:
        """Send a request and report what came back, without raising.

        Returns (adapter text, parsed bytes or None, explanation). Used by the
        probe command, where the failure itself is the interesting part.
        """

        try:
            text = self.send(payload.replace(" ", "").upper(), timeout)
        except ElmError as exc:
            return "", None, str(exc)

        try:
            data = self._parse(text)
        except ElmError as exc:
            return text.strip(), None, str(exc)

        if len(data) >= 3 and data[0] == 0x7F:
            return text.strip(), data, str(NegativeResponse(data[1], data[2]))
        return text.strip(), data, "ok"

    def start_session(self, request: str) -> bytes:
        data = self.request(request)
        expected = bytes.fromhex("50" + request[2:])
        if not data.startswith(expected):
            raise ElmError("Unexpected diagnostic session response")
        return data

    def keep_alive(self, request: str) -> None:
        try:
            self.request(request, timeout=1.0)
        except ElmError as exc:
            log.debug("keep alive failed: %s", exc)

    def close(self) -> None:
        try:
            self.send("AT Z", timeout=1.0)
        except (ElmError, OSError):
            pass
        finally:
            self.io.close()
