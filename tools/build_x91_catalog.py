"""Offline catalog builder; preserves the customized 11075 profile."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renmon.clip.extract import Extractor
from renmon.safety import read_request


def main():
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / "docs/x91-inventory/inventory.json").read_text())[
        "profiles"
    ]
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/build_x91_catalog.py CLIP_ROOT")
    ex = Extractor(sys.argv[1])
    entries = []
    for r in rows:
        if r["ecu"] != "11075":
            p = ex.build(
                dict(
                    ecuname=r["ecu"],
                    doc=r["doc"],
                    ModelId=r["model"],
                    OptimizerId=r["optimizer"],
                    idTx=r["tx"],
                    idRx=r["rx"],
                    startDiagReq=r["session"],
                    keepAliveReq=r["keepalive"],
                )
            )
            raw = asdict(p)
            raw["signals"] = [s for s in raw["signals"] if read_request(s["request"])]
            (root / "profiles" / f"{r['ecu']}.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n"
            )
        entries.append(
            dict(
                ecu=r["ecu"],
                doc=r["doc"],
                file=f"{r['ecu']}.json",
                available=r["metadata_accepted"],
                reason=""
                if r["metadata_accepted"]
                else "Потрібна підтримка keepalive 3E",
                signals=r["accepted"],
                validation="Статично перевірено; потрібна перевірка на автомобілі",
                rules=[x for x in r["identification"] if x["tag"] == "IdByte"],
            )
        )
    (root / "profiles/catalog-x91.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
