"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

from .elm import Elm, ElmError
from .profile import Poller, Profile
from .store import Store
from .transport import open_transport

DEFAULT_PROFILE = Path(__file__).resolve().parent.parent / "profiles"


# -- extract ---------------------------------------------------------------


def cmd_extract(args) -> int:
    from .clip.extract import Extractor, write_profile

    with open(args.saved_ecus, "rb") as fh:
        ecus = pickle.load(fh, encoding="latin1")

    match = [e for e in ecus if e["ecuname"] == args.ecu]
    if not match:
        available = ", ".join(sorted(e["ecuname"] for e in ecus))
        print(f"ecu {args.ecu} not in {args.saved_ecus}\navailable: {available}")
        return 1

    extractor = Extractor(args.clip_root, args.language)
    profile = extractor.build(match[0])
    path = write_profile(profile, args.out or DEFAULT_PROFILE / f"{args.ecu}.json")

    print(f"{profile.doc}")
    print(f"  signals   : {len(profile.signals)}")
    print(f"  requests  : {len({s.request for s in profile.signals})}")
    print(f"  skipped   : {len(extractor.skipped)}")
    for code, why in extractor.skipped:
        print(f"      {code}: {why}")
    print(f"  written   : {path}")
    return 0


# -- list ------------------------------------------------------------------


def cmd_list(args) -> int:
    profile = Profile.load(args.profile)
    signals = profile.search(args.filter) if args.filter else profile.signals
    print(f"{profile.doc}   {len(signals)} signals\n")
    print(f"{'CODE':<9} {'KIND':<10} {'REQUEST':<8} {'UNIT':<8} LABEL")
    for s in sorted(signals, key=lambda s: s.code):
        print(f"{s.code:<9} {s.kind:<10} {s.request:<8} {s.unit:<8} {s.label}")
    return 0


# -- monitor ---------------------------------------------------------------


def _connect(args, profile: Profile) -> Elm:
    transport = open_transport(args.port, baudrate=args.baud, settle=args.settle)
    try:
        elm = Elm(transport)
        rate = elm.probe()
        if rate:
            print(f"adapter at {rate} baud: {elm.identify()}")
        elm.connect(profile.tx_id, profile.rx_id)
        elm.start_session(profile.start_session)
        return elm
    except BaseException:
        transport.close()
        raise


def cmd_monitor(args) -> int:
    profile = Profile.load(args.profile)
    signals = profile.by_code(args.codes) if args.codes else profile.signals
    if not args.codes and len(signals) > 30:
        print(f"refusing to poll all {len(signals)} signals, name some with -c")
        return 1

    store = None
    elm = None
    try:
        if args.db:
            store = Store(args.db)
            store.describe(signals)
            store.start_session(profile.ecu, profile.doc, args.note or "")

        elm = _connect(args, profile)
        poller = Poller(elm, signals)
        print(
            f"polling {len(signals)} signals in {poller.requests_per_cycle} requests, "
            f"ctrl-c to stop\n"
        )

        width = max(len(s.label) for s in signals)
        last_keepalive = time.monotonic()
        cycles = 0

        while True:
            values, errors, elapsed = poller.cycle()
            cycles += 1

            if store:
                store.record(
                    [(s.code, values.get(s.code), errors.get(s.code)) for s in signals]
                )

            stamp = datetime.now().strftime("%H:%M:%S")
            lines = [
                f"  {stamp}   cycle {cycles}   {elapsed * 1000:.0f} ms"
                f"   {poller.requests_per_cycle} req"
            ]
            for s in signals:
                if s.code in values:
                    shown = f"{values[s.code]:>12.2f} {s.unit}"
                else:
                    shown = f"{'--':>12} {errors.get(s.code, '')[:28]}"
                lines.append(f"  {s.code:<8} {s.label:<{width}}  {shown}")

            sys.stdout.write("\033[H\033[J" if not args.plain else "\n")
            print("\n".join(lines))

            if time.monotonic() - last_keepalive > 2.0:
                elm.keep_alive(profile.keep_alive)
                last_keepalive = time.monotonic()

            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        if elm:
            elm.close()
        if store:
            store.close()
    return 0


# -- probe -----------------------------------------------------------------

# CLIP only ever opens 10C0 here, but an EDC17 keeps part of the 24xx range
# behind a wider session. Tried in order, cheapest first.
SESSIONS = [
    ("10C0", "CLIP diagnostic session"),
    ("1003", "extended diagnostic session"),
]


def cmd_probe(args) -> int:
    """Ask one signal directly and show exactly what the ECU answers.

    pyren prints 0 both for a real zero and for a refused read, so this is the
    way to tell those apart.
    """

    profile = Profile.load(args.profile)
    signals = profile.by_code(args.codes)

    transport = open_transport(args.port, baudrate=args.baud, settle=args.settle)
    elm = Elm(transport)
    try:
        rate = elm.probe()
        if rate:
            print(f"adapter at {rate} baud: {elm.identify()}\n")
        elm.connect(profile.tx_id, profile.rx_id)

        for session, description in SESSIONS:
            text, data, why = elm.raw(session)
            opened = data is not None and data and data[0] == 0x50
            print(f"session {session} ({description}): {'open' if opened else why}")
            if not opened:
                continue

            for signal in signals:
                text, data, why = elm.raw(signal.request)
                shown = data.hex(" ").upper() if data else "-"
                print(f"    {signal.code:<8} {signal.request:<8} -> {shown:<28} {why}")
                if data and why == "ok":
                    try:
                        print(
                            f"    {'':<8} {'':<8}    decodes to "
                            f"{signal.decode(data)} {signal.unit}"
                        )
                    except Exception as exc:  # noqa: BLE001 - report, do not crash
                        print(f"    {'':<8} {'':<8}    decode failed: {exc}")
            print()

            if args.first_working:
                break
    finally:
        elm.close()
    return 0


# -- history ---------------------------------------------------------------


def cmd_history(args) -> int:
    store = Store(args.db)
    try:
        rows = store.history(args.code, args.limit)
    finally:
        store.close()
    if not rows:
        print(f"no readings for {args.code}")
        return 1
    print(f"{args.code}   {len(rows)} readings (newest first)\n")
    for at, value in rows:
        print(f"  {datetime.fromtimestamp(at):%Y-%m-%d %H:%M:%S}  {value:>12.2f}")
    return 0


def cmd_sessions(args) -> int:
    store = Store(args.db)
    print(f"{'ID':<5} {'STARTED':<20} {'ECU':<8} {'READINGS':>9}  NOTE")
    try:
        sessions = store.sessions()
    finally:
        store.close()
    for sid, started, ecu, note, count in sessions:
        print(
            f"{sid:<5} {datetime.fromtimestamp(started):%Y-%m-%d %H:%M:%S}  "
            f"{ecu:<8} {count:>9}  {note or ''}"
        )
    return 0


# -- wiring ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="renmon", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="build a profile from the CLIP database")
    ex.add_argument("ecu")
    ex.add_argument("--clip-root", default="../pyren")
    ex.add_argument("--saved-ecus", default="../pyren/pyren/savedEcus.p")
    ex.add_argument("--language", default="GB")
    ex.add_argument("--out")
    ex.set_defaults(func=cmd_extract)

    ls = sub.add_parser("list", help="show signals in a profile")
    ls.add_argument("profile")
    ls.add_argument("-f", "--filter")
    ls.set_defaults(func=cmd_list)

    mon = sub.add_parser("monitor", help="poll signals from the car")
    mon.add_argument("profile")
    mon.add_argument(
        "-p",
        "--port",
        required=True,
        help="COM3 (Windows), /dev/cu.X (macOS), or host:port",
    )
    mon.add_argument("-c", "--codes", nargs="+", help="signal codes, e.g. PR900")
    mon.add_argument("-b", "--baud", type=int, default=38400)
    mon.add_argument("-i", "--interval", type=float, default=0.0)
    mon.add_argument(
        "--settle", type=float, default=2.0, help="pause after opening a bluetooth port"
    )
    mon.add_argument("--db", help="sqlite file to log into")
    mon.add_argument("--note")
    mon.add_argument("--once", action="store_true")
    mon.add_argument("--plain", action="store_true", help="do not clear the screen")
    mon.set_defaults(func=cmd_monitor)

    pr = sub.add_parser("probe", help="ask one signal and show the raw answer")
    pr.add_argument("profile")
    pr.add_argument("-p", "--port", required=True)
    pr.add_argument("-c", "--codes", nargs="+", required=True)
    pr.add_argument("-b", "--baud", type=int, default=38400)
    pr.add_argument("--settle", type=float, default=2.0)
    pr.add_argument(
        "--first-working",
        action="store_true",
        help="stop at the first session that opens",
    )
    pr.set_defaults(func=cmd_probe)

    hist = sub.add_parser("history", help="show logged values for one signal")
    hist.add_argument("code")
    hist.add_argument("--db", required=True)
    hist.add_argument("-n", "--limit", type=int, default=50)
    hist.set_defaults(func=cmd_history)

    ses = sub.add_parser("sessions", help="list logging sessions")
    ses.add_argument("--db", required=True)
    ses.set_defaults(func=cmd_sessions)

    desktop = sub.add_parser("desktop", help="native desktop monitor (no HTTP server)")
    desktop.set_defaults(func=cmd_desktop)
    return parser


def cmd_desktop(args):
    from .desktop import main

    return main()


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(args)
    except (ElmError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
