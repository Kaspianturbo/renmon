import sys
from pathlib import Path
import unittest
import time
import tempfile
from unittest.mock import patch
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon.catalog import Catalog, IdentificationError
from renmon.safety import command, SafetyError
from renmon.elm import Elm, NegativeResponse
from renmon.profile import Profile
from renmon.features.monitoring.service import Monitor

ROOT = Path(__file__).resolve().parents[1]


def identity(entry):
    data = bytearray(18)
    data[:2] = b"\x61\x80"
    for rule in entry["rules"]:
        data[int(rule["rank"]) + 1] = int(rule["value"], 16)
    return bytes(data)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog(ROOT / "profiles")

    def test_all_identities_and_available_profiles(self):
        self.assertEqual(len(self.catalog.entries), 18)
        for e in self.catalog.entries:
            self.assertEqual(self.catalog.identify(identity(e))["ecu"], e["ecu"])
            if e["available"]:
                p = self.catalog.load(e["ecu"])
                self.assertTrue(p.signals)
                self.assertTrue(all(s.request.startswith("22") for s in p.signals))
            else:
                with self.assertRaises(IdentificationError):
                    self.catalog.load(e["ecu"])

    def test_invalid_and_ambiguous(self):
        e = self.catalog.entries[-1]
        good = identity(e)
        for data in (
            b"",
            good[:17],
            b"\x62\x80" + good[2:],
            b"\x7f\x21\x31",
            b"\x61\x80" + bytes(16),
        ):
            with self.assertRaises(IdentificationError):
                self.catalog.identify(data)
        self.catalog.entries.append(e.copy())
        with self.assertRaisesRegex(IdentificationError, "Неоднозначна"):
            self.catalog.identify(good)

    def test_exact_command_and_no_retry(self):
        self.assertEqual(command("2180"), "2180")
        for cmd in (
            "218000",
            "2181",
            "21AC",
            "2180\r1101",
            "1101",
            "3101FF00",
            "2EF19000",
        ):
            with self.assertRaises(SafetyError):
                command(cmd)
        elm = Mock()
        elm.request.side_effect = NegativeResponse(0x21, 0x31)
        with self.assertRaises(NegativeResponse):
            self.catalog.verify(elm)
        elm.request.assert_called_once_with("2180", timeout=5)

    def test_mismatch_and_length_prefixed_reply(self):
        elm = Mock()
        elm.request.return_value = identity(self.catalog.entries[0])
        with self.assertRaises(IdentificationError):
            self.catalog.verify(elm, "11075")
        data = elm.request.return_value
        self.assertEqual(
            Elm(Mock())._parse(bytes([len(data)]).hex() + data.hex()), data
        )

    def test_detection_selects_profile_and_clears_old_samples(self):
        mon = Monitor(Profile.load(ROOT / "profiles/11075.json"))
        try:
            elm = Mock()
            entry = self.catalog.entries[0]
            elm.request.return_value = identity(entry)
            mon.connection.target = "COM12"
            mon.connection.elm = elm
            mon.connection.status = "connected"
            mon.samples.append({"old": True})
            mon.codes = ["PR383"]
            mon.detect({"session": ""})
            self.assertEqual(mon.profile.ecu, entry["ecu"])
            self.assertEqual(mon.codes, [])
            self.assertFalse(mon.samples)
            elm.start_session.assert_not_called()
            elm.request.assert_called_once_with("2180", timeout=5)
            elm.request.return_value = b"\x61\x80" + bytes(16)
            with self.assertRaises(IdentificationError):
                self.catalog.verify(elm)
            with self.assertRaises(ValueError):
                mon.detect({"session": "1086"})
        finally:
            mon.connection.close()

    def test_live_mismatch_never_reads_signals(self):
        from test_windows import MemorySerial

        adapter = MemorySerial("COM12")
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("renmon.features.monitoring.service.ports", return_value=["COM12"]),
            patch("renmon.features.connection.service.sys.platform", "win32"),
            patch(
                "renmon.features.connection.service.SerialTransport",
                return_value=adapter,
            ),
        ):
            mon = Monitor(self.catalog.load("10478"), log_dir=tmp)
            try:
                mon.start(
                    dict(
                        mode="live",
                        port="COM12",
                        codes=[mon.profile.signals[0].code],
                        interval=0.1,
                        session="",
                    )
                )
                mon.thread.join(4)
                self.assertFalse(mon.thread.is_alive())
                self.assertIn("не відповідає", mon.error)
                self.assertFalse(any(c.startswith("22") for c in adapter.commands))
                self.assertEqual(adapter.commands.count("2180"), 1)
                self.assertFalse(mon.samples)
            finally:
                mon.stop()
                mon.thread.join(3)
                mon.connection.close()


if __name__ == "__main__":
    unittest.main()
