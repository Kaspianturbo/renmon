"""Enumerate local serial devices; never accept arbitrary API-provided paths."""

import re
import sys


def ports():
    from serial.tools.list_ports import comports

    devices = {p.device for p in comports()}
    if sys.platform == "win32":
        # pyserial handles the Windows device prefix for COM10 and above.
        return sorted(
            (p for p in devices if re.fullmatch(r"COM[1-9][0-9]*", p)),
            key=lambda p: int(p[3:]),
        )
    if sys.platform == "darwin":
        return sorted(p for p in devices if p.startswith("/dev/cu."))
    return sorted(p for p in devices if p.startswith("/dev/"))
