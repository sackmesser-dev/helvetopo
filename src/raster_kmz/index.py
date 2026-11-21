"""Erzeugt INDEX.md für gebaute Pakete (z. B. work/raster_kmz/ch/).

Liest <root>/<lauf>/<paket>/build.json (+ <paket>_check.json, falls check.py lief) und schreibt
eine Übersicht mit Paketname, Gebiet, Kacheln, MB, Laufzeit, Ausgaben und Prüfstatus.

Aufruf: python3 index.py [work/raster_kmz/ch]
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import build as B

LEVEL_TEXT = {25: "Detail", 50: "Mittel", 100: "Übersicht", 200: "Landesübersicht"}


def main() -> None:
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else B.WORK / "ch"
    runs = sorted((p for p in root.iterdir() if (p / "plan.json").exists()),
                  key=lambda p: json.loads((p / "plan.json").read_text())["scale"])
    out = [f"# Swiss Map Raster als Garmin Custom Maps – Schweiz",
           "",
           f"Stand {dt.date.today().isoformat()}. Kartendaten: **©swisstopo** (Swiss Map Raster, "
           f"Open Government Data, {B.LICENSE_URL}). Keine offizielle Karte von swisstopo.",
           "",
           "Garmin zählt die Kacheln **aller** Custom Maps auf dem Gerät zusammen: GPSMAP 66/67 "
           "und Montana 7xx höchstens 500, ältere Geräte 100. Ein Detailpaket hat bis zu 484 "
           "Kacheln, also ist pro Gerät in der Regel ein Paket gleichzeitig installiert. "
           "Bei vier Grenz- und Seeblättern (SMR25 1035 Bodensee, 1056 Vorarlberg, 1282 "
           "Genfersee, 2220 Vinschgau) ist die neueste frei verfügbare Ausgabe von 1984–2003; "
           "betroffene Pakete sind als „ältere Ausgabe“ gekennzeichnet. "
           "Installation: KMZ nach `\\Garmin\\CustomMaps\\` kopieren, siehe README.txt im Paket.",
           ""]
    summary = []
    sections = []
    for run in runs:
        plan = json.loads((run / "plan.json").read_text())
        rows, tot_t, tot_mb, tot_s, bad, missing = [], 0, 0.0, 0.0, 0, 0
        old_rows = []
        for pp in plan["packages"]:
            d = run / f"smr{plan['scale']}-{pp['id']}"
            bj = d / "build.json"
            if not bj.exists():
                missing += 1
                rows.append(f"| `smr{plan['scale']}-{pp['id']}` | {', '.join(pp['cantons'])} "
                            f"| – | {pp['n']} (geplant) | – | – | – | fehlt |")
                continue
            m = json.loads(bj.read_text())
            cj = d / f"{m['name']}_check.json"
            status = "–"
            if cj.exists():
                ok = json.loads(cj.read_text())["ok"]
                status = "OK" if ok else "FEHLER"
                bad += not ok
            w, s, e, n = m["bbox"]
            rows.append(f"| `{m['name']}.kmz` | {', '.join(m['cantons'])} | "
                        f"{w:.2f}–{e:.2f} O, {s:.2f}–{n:.2f} N | {m['tiles']} | {m['kmz_mb']:.1f} | "
                        f"{m.get('seconds', 0):.0f} | {B.years_text(m['years']).split(' (')[0]} | {status} |")
            if m.get("old_sheets"):
                old_rows.append(f"- `{m['name']}.kmz`: " + ", ".join(f"`{x}`" for x in m["old_sheets"]))
            tot_t += m["tiles"]; tot_mb += m["kmz_mb"]; tot_s += m.get("seconds", 0)
        rel = run.relative_to(root)
        sc = plan["scale"]
        summary.append(f"| SMR{sc} ({LEVEL_TEXT.get(sc, '')}) | {plan['res_m']} m | "
                       f"{len(plan['packages'])} | {tot_t} | {tot_mb / 1024:.1f} GB | "
                       f"{tot_s / 60:.0f} min | {missing} | {bad} |")
        sections += [f"## SMR{sc} – {LEVEL_TEXT.get(sc, '')} ({plan['res_m']} m/px)", "",
                     f"Schema {plan['scheme']}, Limit {plan['limit']} Kacheln, Block "
                     f"{plan['block']} × {plan['block']}. Paketkarte: [`{rel}/uebersicht.png`]"
                     f"({rel}/uebersicht.png)", "",
                     "| Paket | Gebiet (Kantone) | Ausdehnung | Kacheln | MB | Laufzeit s | Ausgabe | Prüfung |",
                     "|---|---|---|---|---|---|---|---|", *rows, ""]
        if old_rows:
            sections += ["Pakete mit **älterer Ausgabe** (Grenz-/Seeblätter, deren neueste frei "
                         "verfügbare Ausgabe vor 2010 liegt; keine kostenpflichtige Altversion):",
                         "", *old_rows, ""]
    out += ["## Übersicht", "",
            "| Stufe | Auflösung | Pakete | Kacheln | Grösse | Rechenzeit | fehlend | Prüffehler |",
            "|---|---|---|---|---|---|---|---|", *summary, "", *sections]
    (root / "INDEX.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(root / "INDEX.md")


if __name__ == "__main__":
    main()
