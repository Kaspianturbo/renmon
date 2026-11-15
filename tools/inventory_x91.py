"""Offline X91 engine inventory. Never opens a transport or changes live profiles."""

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon.clip.extract import Extractor
from renmon.profile import Signal
from renmon.safety import KEEPALIVE, SESSIONS, read_request


def main():
    p = argparse.ArgumentParser()
    p.add_argument("clip_root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    vehicle_path = a.clip_root / "Vehicles/TCOM_132.xml"
    uces_path = a.clip_root / "EcuRenault/Uces.xml"
    vehicle = ET.parse(vehicle_path).getroot()
    uces = {e.get("name"): e for e in ET.parse(uces_path).getroot()}
    extractor = Extractor(a.clip_root)
    rows = []
    sources = {vehicle_path, uces_path, a.clip_root / "Location/DiagOnCAN_GB.bqm"}
    for network in vehicle.iter("CANNetwork"):
        for family in network.iter("EcuKind"):
            if family.get("idFamily") != "1":
                continue
            for ref in family.findall("EcuRef"):
                ident = ref.get("name")
                ecu = uces[ident]
                info = ecu.find("ECUInformations")
                address = info.find("Address").get("targetAddress")
                can = next(
                    c
                    for c in network.iter("CanId")
                    if c.get("targetAddress") == address
                )
                meta = dict(
                    ecuname=ident,
                    doc=ref.get("doc"),
                    ModelId=ecu.findtext("ModelId"),
                    OptimizerId=ecu.findtext("OptimizerId"),
                    idTx=f"{int(can.get('idTx'), 16):03X}",
                    idRx=f"{int(can.get('idRx'), 16):03X}",
                    startDiagReq=info.find("Frames/StartDiagSession").get("request"),
                    keepAliveReq=info.find("Frames/KeepAlive").get("request"),
                )
                row = dict(
                    ecu=ident,
                    doc=ref.get("doc"),
                    model=meta["ModelId"],
                    optimizer=meta["OptimizerId"],
                    std_type=ecu.get("stdType"),
                    network=network.attrib,
                    brp=[n.attrib for n in network.iter("CANNetworkParams")],
                    tx=meta["idTx"],
                    rx=meta["idRx"],
                    session=meta["startDiagReq"],
                    keepalive=meta["keepAliveReq"],
                    identification=[
                        dict(tag=n.tag, **n.attrib) for n in info.find("Ids")
                    ],
                )
                fg_path = extractor.sessions / (meta["ModelId"][:-3] + "xml")
                sg_path = extractor.sessions / (meta["OptimizerId"][:-3] + "xml")
                sources.update([fg_path, sg_path])
                overlay = sg_path.with_suffix(".add.xml")
                if overlay.exists():
                    sources.add(overlay)
                try:
                    fg = ET.parse(fg_path).getroot()
                    nodes = [
                        n
                        for container, tag in [
                            ("Parameters", "Parameter"),
                            ("States", "State"),
                        ]
                        for section in fg.findall(".//" + container)
                        for n in section.findall(tag)
                    ]
                    row["metadata_accepted"] = (
                        meta["startDiagReq"] in SESSIONS
                        and meta["keepAliveReq"] in KEEPALIVE
                    )
                    row["defined"] = len(nodes)
                    row["freeze_frame"] = sum(
                        (n.get("agcdRef") or "").endswith("FF") for n in nodes
                    )
                    profile = extractor.build(meta)
                    row["extracted"] = len(profile.signals)
                    row["skipped"] = extractor.skipped
                    row["no_live_value"] = (
                        len(nodes)
                        - row["freeze_frame"]
                        - len(profile.signals)
                        - len(extractor.skipped)
                    )
                    row["services"] = dict(
                        Counter(s.request[:2] for s in profile.signals)
                    )
                    row["requests"] = sorted({s.request for s in profile.signals})
                    row["accepted"] = 0
                    row["compile_errors"] = []
                    for s in profile.signals:
                        if read_request(s.request):
                            try:
                                Signal(**asdict(s))
                                row["accepted"] += 1
                            except Exception as e:
                                row["compile_errors"].append([s.code, str(e)])
                    row["blocked"] = [
                        dict(code=s.code, request=s.request)
                        for s in profile.signals
                        if not read_request(s.request)
                    ]
                    row["pr415"] = [
                        asdict(s) for s in profile.signals if s.code == "PR415"
                    ]
                    row["signals"] = [
                        dict(
                            code=s.code,
                            kind=s.kind,
                            label=s.label,
                            unit=s.unit,
                            request=s.request,
                            positive=s.positive,
                        )
                        for s in profile.signals
                    ]
                    assert (
                        row["defined"]
                        == row["freeze_frame"]
                        + row["extracted"]
                        + len(row["skipped"])
                        + row["no_live_value"]
                    )
                except Exception as e:
                    row["error"] = f"{type(e).__name__}: {e}"
                rows.append(row)
                print(
                    ident,
                    row.get("defined"),
                    row.get("extracted"),
                    row.get("accepted"),
                    row.get("services"),
                    "skips",
                    len(row.get("skipped", [])),
                    row.get("error", ""),
                    flush=True,
                )
    manifest = [
        {"path": str(f), "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
        for f in sorted(sources)
        if f.exists()
    ]
    result = dict(
        scope="Local CLIP X91 engine references only; offline static audit, no vehicle verification",
        vehicle=vehicle.attrib,
        profiles=rows,
        sources=manifest,
    )
    (a.output / "inventory.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    lines = [
        "# Інвентаризація ECU двигуна Laguna III / X91",
        "",
        "Статичний аудит локальної CLIP-бази. Адаптер не використовувався. Робочий профіль Renmon і політика команд не змінені.",
        "",
        "| ECU | Назва в базі | Визначено | Витягнуто | Приймає Renmon¹ | Сервіси сигналів | Пропущено з помилкою |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['ecu']} | {r['doc']} | {r.get('defined', '—')} | {r.get('extracted', '—')} | {r.get('accepted', '—')} | {r.get('services', {})} | {len(r.get('skipped', []))} |"
        )
    lines += [
        "",
        "¹ Пройшли фільтр запиту `22` + один DID та компіляцію формули. Це не перевірка правильності декодування або роботи на автомобілі. «Визначено» включає freeze frame та записи без живого значення; вони не рівнозначні датчикам, доступним для моніторингу.",
        "",
        "## Ідентифікація",
        "",
        "Числа rank, mask, value нижче збережені дослівно з Uces.xml. Семантику індексування треба відтворити за Pyren перед реалізацією.",
        "",
        "| ECU | FG / SG | Сесія / keepalive | Умови ідентифікації |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['ecu']} | {r['model']} / {r['optimizer']} | {r['session']} / {r['keepalive']} | `"
            + json.dumps(r["identification"], ensure_ascii=False)
            + "` |"
        )
    lines += ["", "## Пропущені записи", ""]
    for r in rows:
        counts = Counter(reason for _, reason in r.get("skipped", []))
        lines.append(
            f"- **{r['ecu']}**: freeze frame {r.get('freeze_frame')}; без живого значення {r.get('no_live_value')}; причини помилок: {dict(counts)}; помилки компіляції: {r.get('compile_errors', [])}."
        )
    lines += [
        "",
        "## Відтворення",
        "",
        "```sh",
        "python3 tools/inventory_x91.py ../pyren docs/x91-inventory",
        "```",
        "",
        "Деталі кожного сигналу, запити, пропуски, PR415 та SHA-256 джерел: `inventory.json`. Скрипт читає лише локальні файли та створює звіт.",
    ]
    (a.output / "INVENTORY.uk.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
