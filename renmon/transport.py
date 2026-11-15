"""Byte level links to an ELM327: serial (usb/bluetooth) or tcp (wifi)."""

from __future__ import annotations

import socket
import time
from typing import Protocol


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...
    def read(self, size: int = 1) -> bytes: ...
    def reset_input(self) -> None: ...
    def close(self) -> None: ...


class SerialTransport:
    """Serial port, which on macOS is also how bluetooth SPP appears.

    Opening a bluetooth ``/dev/cu.*`` returns before the RFCOMM link is really
    up, so the first exchange can vanish. ``settle`` gives the link a moment.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 38400,
        timeout: float = 5.0,
        settle: float = 0.0,
    ):
        import serial  # imported lazily so tcp only setups need no pyserial

        self._port = serial.Serial(
            port, baudrate=baudrate, timeout=timeout, write_timeout=2
        )
        if settle:
            time.sleep(settle)
            self._port.reset_input_buffer()

    @property
    def baudrate(self) -> int:
        return self._port.baudrate

    @baudrate.setter
    def baudrate(self, value: int) -> None:
        self._port.baudrate = value

    def write(self, data: bytes) -> None:
        self._port.write(data)

    def read(self, size: int = 1) -> bytes:
        return self._port.read(size)

    def reset_input(self) -> None:
        self._port.reset_input_buffer()

    def close(self) -> None:
        self._port.close()


class TcpTransport:
    """WiFi adapters, typically 192.168.0.10:35000."""

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock.settimeout(timeout)

    def write(self, data: bytes) -> None:
        self._sock.sendall(data)

    def read(self, size: int = 1) -> bytes:
        try:
            data = self._sock.recv(size)
            if not data:
                raise ConnectionError("ELM TCP connection closed")
            return data
        except socket.timeout:
            return b""

    def reset_input(self) -> None:
        timeout = self._sock.gettimeout()
        self._sock.settimeout(0.01)
        try:
            while self._sock.recv(4096):
                pass
        except OSError:
            pass
        finally:
            self._sock.settimeout(timeout)

    def close(self) -> None:
        self._sock.close()


def open_transport(
    target: str, baudrate: int = 38400, settle: float = 0.0
) -> Transport:
    """``host:port`` opens tcp, anything else is treated as a serial device."""

    if ":" in target and not target.startswith("/"):
        host, _, port = target.rpartition(":")
        return TcpTransport(host, int(port))
    return SerialTransport(target, baudrate=baudrate, settle=settle)
