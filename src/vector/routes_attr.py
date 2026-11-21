"""Routenzugehörigkeit (SchweizMobil/ASTRA) als Kanten-Attribute an den TLM-Strassen.

Eingabe: CSV aus src/routes/match_tlm.py (routes-overlay), Spalten
uuid,objektart,wanderwege,belagsart,wanderland,veloland,mountainbikeland,skatingland
mit Werten `netz:nummer;…`. Empfehlung und Begründung: docs/vektor/routen.md.

Lizenzfolge: Mit diesen Attributen gehört „Bundesamt für Strassen, Kanton, Stiftung SchweizMobil“
in die Quellenangabe der Basiskarte (build_img.sh liest dazu <pbf>.sources).
"""

from __future__ import annotations

import csv
import logging
from collections import Counter
from pathlib import Path

log = logging.getLogger("vector")

ASTRA_SOURCE = "Bundesamt für Strassen, Kanton, Stiftung SchweizMobil"
# Gesetzliche/bauliche Sperren haben Vorrang vor bicycle=designated
LEGAL_BLOCK = {"Gesperrt", "Militaerstrasse", "Panzerpiste", "Rennstrecke", "Teststrecke",
               "Gesicherte Kletterpartie"}
NET_RANK = {"national": 3, "regional": 2, "local": 1}


def load(path: Path) -> dict[str, dict[str, str]]:
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[r["uuid"].strip("{}").upper()] = r
    log.info("Routenzuordnung: %d TLM-Kanten aus %s", len(out), path)
    return out


def _best_net(v: str) -> str | None:
    nets = [p.split(":", 1)[0] for p in v.split(";") if p]
    nets = [n for n in nets if n in NET_RANK]
    return max(nets, key=NET_RANK.get) if nets else None


def apply(tags: dict, r: dict, stats: Counter) -> None:
    velo, mtb = r.get("veloland", ""), r.get("mountainbikeland", "")
    skate, wander = r.get("skatingland", ""), r.get("wanderland", "")
    if velo:
        tags["ch:veloland"] = velo
        best = _best_net(velo)
        if best:
            tags[{"national": "ncn", "regional": "rcn", "local": "lcn"}[best]] = "yes"
            tags["route_bicycle"] = best
    if mtb:
        tags["ch:mountainbikeland"] = mtb
        tags["mtb"] = "designated"
        best = _best_net(mtb)
        if best:
            tags["route_mtb"] = best
    if skate:
        tags["ch:skatingland"] = skate
        tags["inline_skates"] = "designated"
    if wander:
        tags["ch:wanderland"] = wander
    if velo or mtb:
        if tags.get("swisstopo:verkehrsbeschraenkung") in LEGAL_BLOCK or tags.get("access") in ("no", "private"):
            stats["konflikt_sperre"] += 1
            log.debug("Velo-/MTB-Route auf gesperrter Kante %s (%s)", tags.get("swisstopo:uuid"),
                      tags.get("swisstopo:verkehrsbeschraenkung"))
        elif tags.get("highway") in ("motorway", "motorway_link"):
            stats["konflikt_autobahn"] += 1
        else:
            if tags.get("bicycle") == "no":
                stats["bicycle_no_aufgehoben"] += 1
            tags["bicycle"] = "designated"
    stats["kanten"] += 1
