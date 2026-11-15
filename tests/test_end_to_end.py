"""Full path against the fake ELM: connect, poll, decode, store."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fake_elm import FakeElm  # noqa: E402
from renmon.elm import Elm  # noqa: E402
from renmon.profile import Poller, Profile  # noqa: E402
from renmon.store import Store  # noqa: E402
from renmon.transport import SerialTransport  # noqa: E402

# 62 <did> <data> - values chosen so the expected result is easy to check
CANNED = {
    "2224A9": bytes.fromhex("6224A9" + "02F3B2"),  # 193458 km, 24 bit
    "22242C": bytes.fromhex("62242C" + "04D2"),  # 1234/100 = 12.34 g
    "2224A5": bytes.fromhex("6224A5" + "0141"),  # 321/100 = 3.21 g
    "222006": bytes.fromhex("222006"[:0] + "62200602F41A"),  # 193562 km
    "222001": bytes.fromhex("622001" + "0BB8"),  # (3000-2730)/10 = 27.0 C
}

EXPECTED = {
    "PR900": 193458.0,
    "PR383": 12.34,
    "PR1012": 3.21,
    "PR992": 193562.0,
    "PR064": 27.0,
}


def main() -> int:
    profile = Profile.load(ROOT / "profiles" / "11075.json")
    codes = list(EXPECTED)
    signals = profile.by_code(codes)

    fake = FakeElm(CANNED)
    print(f"fake adapter on {fake.device}")

    elm = Elm(SerialTransport(fake.device, baudrate=38400, timeout=2.0))
    rate = elm.probe()
    print(f"probe -> {rate} baud, id={elm.identify()}")
    elm.connect(profile.tx_id, profile.rx_id)
    elm.start_session(profile.start_session)

    poller = Poller(elm, signals)
    values, errors, elapsed = poller.cycle()
    print(f"cycle: {poller.requests_per_cycle} requests in {elapsed * 1000:.1f} ms")

    store = Store(ROOT / "tests" / "_tmp.sqlite")
    store.describe(signals)
    store.start_session(profile.ecu, profile.doc, "self test")
    store.record([(s.code, values.get(s.code), errors.get(s.code)) for s in signals])

    failures = 0
    print()
    for signal in signals:
        got = values.get(signal.code)
        want = EXPECTED[signal.code]
        ok = got is not None and abs(got - want) < 1e-6
        failures += not ok
        mark = "ok  " if ok else "FAIL"
        print(
            f"  {mark} {signal.code:<8} {signal.label:<44} "
            f"got={got} want={want} {errors.get(signal.code, '')}"
        )

    rows = store.history("PR900")
    print(f"\n  sqlite: {len(rows)} row(s) for PR900 -> {rows}")
    failures += not rows

    print(f"\n  requests seen by the adapter: {fake.requests}")
    store.close()
    elm.close()
    fake.close()
    (ROOT / "tests" / "_tmp.sqlite").unlink(missing_ok=True)

    print("\nFAILURES:" if failures else "\nall good")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
