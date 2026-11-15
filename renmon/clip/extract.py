"""Build a flat monitoring profile out of the CLIP database.

Everything Renault specific happens here, once, offline. The result is a plain
json file the runtime can use without knowing anything about CLIP.

Chain for a single parameter::

    FG: <Parameter name="P022" agcdRef="PR383" codeMR="PR383">
    SG: Parameter\\P022  -> formula + mnemonic names
    SG: Mnemonic\\<name> -> type, bitsLength, service id
    SG: Service\\<sid>   -> request bytes, positive reply, startByte/startBit
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .formula import FormulaError, to_python
from .optfile import OptFile


@dataclass
class Signal:
    """One readable quantity."""

    code: str  # PR900, ET824 ...
    name: str  # internal CLIP id, P900
    kind: str  # parameter | state
    label: str
    unit: str
    request: str  # "2224A9"
    positive: str  # expected first reply byte, "62"
    formula: str  # python expression over m0, m1 ...
    sources: list[dict] = field(default_factory=list)
    interpretations: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class Profile:
    ecu: str
    model_id: str
    optimizer_id: str
    doc: str
    tx_id: str
    rx_id: str
    start_session: str
    keep_alive: str
    signals: list[Signal] = field(default_factory=list)
    did_lengths: dict[str, int] = field(default_factory=dict)


class ExtractionError(RuntimeError):
    pass


def _text(entry: str | None) -> ET.Element:
    if entry is None:
        raise ExtractionError("missing optimizer entry")
    return ET.fromstring(entry)


class Extractor:
    def __init__(self, clip_root: str | Path, language: str = "GB"):
        self.root = Path(clip_root)
        sessions = self.root / "EcuRenault" / "Sessions"
        if not sessions.is_dir():
            raise ExtractionError(f"no EcuRenault/Sessions under {self.root}")
        self.sessions = sessions
        self.translations = OptFile(
            self.root / "Location" / f"DiagOnCAN_{language}.bqm"
        ).entries

    # -- helpers ---------------------------------------------------------

    def _label(self, element: ET.Element | None) -> str:
        if element is None:
            return ""
        code = element.get("codetext", "")
        if code and code in self.translations:
            return self.translations[code].strip()
        return (element.get("defaultText") or "").strip()

    def _service(self, opt: OptFile, sid: str) -> tuple[str, str, dict]:
        """Return (request, positive reply byte, {mnemo name: location})."""

        node = _text(opt.get("Service", sid))
        request_node = node.find(".//Request")
        if request_node is None:
            raise ExtractionError(f"service {sid} has no request")
        request = (request_node.get("val") or "").strip().upper()

        simple = node.find(".//Simple")
        positive = (simple.get("val") if simple is not None else "") or ""

        locations = {}
        for loc in node.iter("MnemoLocation"):
            locations[loc.get("name")] = {
                "start_byte": int(loc.get("startByte") or 1),
                "start_bit": int(loc.get("startBit") or 0),
            }
        return request, positive.upper(), locations

    def _mnemonic(self, opt: OptFile, name: str) -> dict:
        node = _text(opt.get("Mnemonic", name))
        datas = node.find("MnemoDatas")
        if datas is None:
            raise ExtractionError(f"mnemonic {name} has no MnemoDatas")

        sids = [s.get("name") for s in node.iter("ServiceID")]
        if not sids:
            raise ExtractionError(f"mnemonic {name} is not readable")

        request, positive, locations = self._service(opt, sids[0])
        if name not in locations:
            raise ExtractionError(f"mnemonic {name} absent from service {sids[0]}")

        return {
            "mnemonic": name,
            "type": datas.get("type") or "UNUM8",
            "bits": int(datas.get("bitsLength") or 8),
            "little_endian": (datas.get("littleEndian") or "0") != "0",
            "request": request,
            "positive": positive,
            **locations[name],
        }

    # -- main ------------------------------------------------------------

    def build(self, ecu: dict) -> Profile:
        model_id = ecu["ModelId"].strip()
        optimizer_id = ecu["OptimizerId"].strip()

        fg_path = self.sessions / (model_id[:-3] + "xml")
        sg_path = self.sessions / (optimizer_id[:-3] + "xml")
        opt = OptFile(sg_path)

        overlay = sg_path.with_suffix(".add.xml")
        if overlay.is_file():
            for node in ET.parse(overlay).getroot():
                key = node.get("id") or node.get("serviceID") or node.get("name")
                if key:
                    opt.entries[f"{node.tag}\\{key}"] = ET.tostring(
                        node, encoding="unicode"
                    )

        fg = ET.parse(fg_path).getroot()
        profile = Profile(
            ecu=ecu["ecuname"],
            model_id=model_id,
            optimizer_id=optimizer_id,
            doc=ecu.get("doc", ""),
            tx_id=ecu["idTx"],
            rx_id=ecu["idRx"],
            start_session=ecu.get("startDiagReq", "10C0"),
            keep_alive=ecu.get("keepAliveReq", "3E01"),
        )

        data_ids = opt.entries.get("DataIds")
        if data_ids:
            for node in ET.fromstring(data_ids).iter("DataId"):
                bits = int(node.get("dataBitLength"))
                if bits > 0 and bits % 8 == 0:
                    profile.did_lengths[node.get("id").upper()] = bits // 8

        skipped: list[tuple[str, str]] = []
        for kind, container, tag in (
            ("parameter", "Parameters", "Parameter"),
            ("state", "States", "State"),
        ):
            section = fg.find(f".//{container}")
            if section is None:
                continue
            for node in section.findall(tag):
                try:
                    signal = self._signal(opt, node, kind)
                except (ExtractionError, FormulaError, ET.ParseError) as exc:
                    skipped.append((node.get("codeMR") or node.get("name"), str(exc)))
                    continue
                if signal is not None:
                    profile.signals.append(signal)

        self.skipped = skipped
        return profile

    def _signal(self, opt: OptFile, node: ET.Element, kind: str) -> Signal | None:
        name = node.get("name")
        code = node.get("codeMR") or node.get("agcdRef") or name
        agcd = node.get("agcdRef") or ""

        # *_FF entries are freeze frame copies, they are not live readable
        if agcd.endswith("FF"):
            return None

        computation = _text(opt.get(node.tag, name))
        value_node = computation.find(".//Value")
        if value_node is None or not (value_node.text or "").strip():
            return None

        mnemo_names = [m.get("name") for m in computation.iter("Mnemo")]
        if not mnemo_names:
            return None

        sources = [self._mnemonic(opt, m) for m in mnemo_names]
        if any(s["little_endian"] for s in sources):
            raise ExtractionError("little endian mnemonics are not supported yet")

        requests = {s["request"] for s in sources}
        if len(requests) > 1:
            raise ExtractionError(f"spans several requests: {sorted(requests)}")

        expression = to_python(value_node.text, mnemo_names)

        return Signal(
            code=code,
            name=name,
            kind=kind,
            label=self._label(node.find("Label")),
            unit=self._label(node.find("Unit")),
            request=sources[0]["request"],
            positive=sources[0]["positive"],
            formula=expression,
            sources=sources,
            interpretations={
                c.get("value"): {"label": self._label(c)}
                for c in node.findall("Interpretation/Correspondance")
            },
        )


def write_profile(profile: Profile, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
