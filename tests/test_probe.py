"""Probe against an ECU that refuses 24A9 in the CLIP session.

Reproduces what pyren shows as a plain 0: the read is rejected, not zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fake_elm import FakeElm  # noqa: E402
from renmon.cli import main  # noqa: E402

CANNED = {
    "2224A9": bytes.fromhex("6224A9" + "02F3B2"),  # 193458 km
    "22242C": bytes.fromhex("62242C" + "04D2"),  # 12.34 g
}

# 24A9 only answers in the extended session, 242C answers in both
SESSIONS = {
    "10C0": {"22242C"},
    "1003": {"22242C", "2224A9"},
}


def run() -> int:
    fake = FakeElm(CANNED, sessions=SESSIONS)
    print(f"fake adapter on {fake.device}, 24A9 restricted to 1003\n")
    rc = main(
        [
            "probe",
            str(ROOT / "profiles" / "11075.json"),
            "-p",
            fake.device,
            "-c",
            "PR900",
            "PR383",
        ]
    )
    fake.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(run())
