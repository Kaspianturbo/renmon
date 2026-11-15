"""Local X91 catalog and strict, read-only 2180 identification."""

import json
from pathlib import Path

from .profile import Profile


class IdentificationError(ValueError):
    pass


class Catalog:
    def __init__(self, directory):
        self.directory = Path(directory)
        path = self.directory / "catalog-x91.json"
        self.entries = json.loads(path.read_text()) if path.exists() else []

    def load(self, ecu):
        entry = next((e for e in self.entries if e["ecu"] == ecu), None)
        if entry is None:
            raise IdentificationError("Невідомий профіль X91")
        if not entry["available"]:
            raise IdentificationError(entry["reason"])
        # Paths come only from the installed catalog, never from HTTP input.
        path = self.directory / entry["file"]
        if path.resolve().parent != self.directory.resolve():
            raise IdentificationError("Некоректний шлях профілю")
        profile = Profile.load(path)
        if profile.ecu != ecu or (profile.tx_id, profile.rx_id) != ("7E0", "7E8"):
            raise IdentificationError("Профіль не відповідає каталогу X91")
        return profile

    def identify(self, payload):
        if not payload.startswith(b"\x61\x80"):
            raise IdentificationError("Очікувалась відповідь 61 80 на запит 2180")
        # Pyren removes only the 61 service byte before applying IdByte.rank.
        # rank 0 therefore refers to 80; rank 6/16 => full payload index 7/17.
        data = payload[1:]
        if len(data) <= 16:
            raise IdentificationError("Закоротка відповідь 2180: ECU не визначено")
        matches = [
            e
            for e in self.entries
            if e["rules"]
            and all(
                0 <= int(rule["rank"]) < len(data)
                and data[int(rule["rank"])] & int(rule["mask"], 16)
                == int(rule["value"], 16)
                for rule in e["rules"]
            )
        ]
        if not matches:
            raise IdentificationError(
                "Невідомий ECU: відповідності в каталозі X91 немає"
            )
        if len(matches) != 1:
            raise IdentificationError("Неоднозначна відповідь ECU: профіль не вибрано")
        return matches[0]

    def verify(self, elm, expected=None):
        # One request. No retries, scans, session escalation or writes.
        entry = self.identify(elm.request("2180", timeout=5))
        if expected is not None and entry["ecu"] != expected:
            raise IdentificationError(
                f"ECU {entry['ecu']} не відповідає вибраному профілю {expected}"
            )
        return entry
