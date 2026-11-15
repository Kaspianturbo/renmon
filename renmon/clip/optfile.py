"""Reader for the packed CLIP optimizer files (SG*.xml, *.bqm).

Python 3 port of pyren's mod_optfile. The format is a flat key/value store of
xml fragments, obfuscated with a position dependent xor. Layout:

    0x00        first byte, 0x55 or 0xBD when obfuscated
    0x14        protlen (u32)
    0x18+2*protlen  keyoff (u32), start of the index
    keyoff-8    tb (u32), end of the index

Each index entry is 12 bytes (addr, strl, keyl) followed by the key itself as
utf-16le. `addr` points at the value, `strl`/`keyl` are lengths in characters.
"""

from __future__ import annotations

import struct
from pathlib import Path

_XOR = 0x5555


class OptFile:
    """Parsed optimizer file: a dict of ``"Tag\\id" -> xml fragment``."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.obfuscated = True
        self.entries: dict[str, str] = {}
        with self.path.open("rb") as fh:
            self._read(fh)

    # -- primitives ------------------------------------------------------

    def _u16(self, fh) -> int:
        pos = fh.tell()
        value = struct.unpack("<H", fh.read(2))[0]
        if not self.obfuscated:
            return value
        return value ^ (pos & 0xFFFF) ^ _XOR

    def _u32(self, fh) -> int:
        return self._u16(fh) + (self._u16(fh) << 16)

    def _text(self, fh, length: int) -> str:
        pos = fh.tell()
        raw = fh.read(2 * length)
        out = []
        for j in range(0, 2 * length, 2):
            ch = struct.unpack("<H", raw[j : j + 2])[0]
            if self.obfuscated:
                ch ^= ((pos + j) & 0xFFFF) ^ _XOR
            out.append(chr(ch))
        return "".join(out)

    # -- container -------------------------------------------------------

    def _read(self, fh) -> None:
        first = fh.read(1)[0]
        if first not in (0x55, 0xBD):
            self.obfuscated = False

        fh.seek(0x14)
        protlen = self._u32(fh)
        fh.seek(0x18 + protlen * 2)
        keyoff = self._u32(fh)

        fh.seek(keyoff - 8)
        end = self._u32(fh)

        pos = keyoff
        while pos < end:
            fh.seek(pos)
            addr = self._u32(fh)
            strl = self._u32(fh)
            keyl = self._u32(fh)

            key = self._text(fh, keyl)

            fh.seek(addr)
            value = self._text(fh, strl).strip().strip("\n")
            # CLIP stores quotes as guillemets
            value = value.replace("\xab", '"').replace("\xbb", '"')

            self.entries[key] = value
            pos += 12 + keyl * 2

    # -- access ----------------------------------------------------------

    def get(self, tag: str, ident: str) -> str | None:
        return self.entries.get(f"{tag}\\{ident}")

    def keys_of(self, tag: str) -> list[str]:
        prefix = tag + "\\"
        return [k[len(prefix) :] for k in self.entries if k.startswith(prefix)]

    def __len__(self) -> int:
        return len(self.entries)
