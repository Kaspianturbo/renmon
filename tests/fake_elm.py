"""A fake ELM327 with an EDC17 behind it, exposed on a pty.

Enough to exercise the whole path offline: baud probing, AT setup, the
diagnostic session and 22xxxx reads with known payloads.
"""

from __future__ import annotations

import os
import pty
import threading


class FakeElm:
    def __init__(
        self,
        data: dict[str, bytes],
        link_delay: float = 0.0,
        sessions: dict[str, set[str]] | None = None,
    ):
        self.data = {k.upper(): v for k, v in data.items()}
        self.link_delay = link_delay
        # {session: {requests allowed in it}}; None means everything is open
        self.sessions = sessions
        self.session = None
        self.master, slave = pty.openpty()
        self.device = os.ttyname(slave)
        self._slave = slave
        self.requests: list[str] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _reply(self, line: str) -> str:
        command = line.strip().upper().replace(" ", "")
        if not command:
            return ""
        if command.startswith("AT"):
            if command in ("ATZ", "ATI"):
                return "ELM327 v1.5"
            return "OK"

        self.requests.append(command)
        if command.startswith("10"):  # start diagnostic session
            if self.sessions is not None and command not in self.sessions:
                return "7F1012"  # sub function not supported
            self.session = command
            return "50" + command[2:]
        if command.startswith("3E"):  # keep alive
            return "7E" + command[2:]
        if command in self.data:
            if self.sessions is not None:
                allowed = self.sessions.get(self.session, set())
                if command not in allowed:
                    return "7F2231"  # request out of range
            return self.data[command].hex().upper()
        return "NO DATA"

    def _serve(self) -> None:
        buffer = ""
        while not self._stop.is_set():
            try:
                chunk = os.read(self.master, 256)
            except OSError:
                return
            if not chunk:
                return
            buffer += chunk.decode("ascii", "ignore")
            while "\r" in buffer:
                line, _, buffer = buffer.partition("\r")
                answer = self._reply(line)
                payload = (answer + "\r\r>") if answer else "\r>"
                os.write(self.master, payload.encode())

    def close(self) -> None:
        self._stop.set()
        os.close(self._slave)
