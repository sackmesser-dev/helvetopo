"""Adresspunkte aus dem amtlichen Gebäudeadressverzeichnis (für mkgmap --housenumbers)."""

from __future__ import annotations

import csv
import logging
from collections import Counter

import numpy as np
import shapely

from .admin import AdminLookup, is_in_tags
from .common import ADDRESS_CSV, CANTON_NAMES, Area, clip_wgs84

log = logging.getLogger("vector")


def add_addresses(b, area: Area, admin: AdminLookup, road_index=None) -> None:
    x0, y0, x1, y1 = area.lv95_bbox()
    rows = []
    with open(ADDRESS_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["ADR_STATUS"] != "real":
                continue
            try:
                x = float(r["ADR_EASTING"])
                y = float(r["ADR_NORTHING"])
            except ValueError:
                continue
            if x0 <= x <= x1 and y0 <= y <= y1 and r["STN_LABEL"] and r["ADR_NUMBER"]:
                rows.append((x, y, r))
    log.info("Adressen im Gebiet (real): %d", len(rows))
    if not rows:
        return
    pts_lv = shapely.points(np.array([(x, y) for x, y, _ in rows]))
    gem, kt, cc = admin.lookup_points(pts_lv)
    if road_index is not None:
        link_area_streets(b, pts_lv, [r["STN_LABEL"].strip() for _, _, r in rows], road_index)
    pts = clip_wgs84(pts_lv, area)
    n = 0
    for i, g in enumerate(pts):
        if g is None or g.is_empty:
            continue
        r = rows[i][2]
        zip_label = r["ZIP_LABEL"].strip()
        plz, _, ort = zip_label.partition(" ")
        t = {
            "addr:street": r["STN_LABEL"].strip(),
            "addr:housenumber": r["ADR_NUMBER"].strip(),
            "addr:postcode": plz,
            "addr:city": r["COM_NAME"].strip(),
            "swisstopo:ortschaft": ort.strip(),
            "swisstopo:egaid": r["ADR_EGAID"],
            "swisstopo:layer": "amtliches-gebaeudeadressverzeichnis",
            "source": "swisstopo",
            "name": r["BDG_NAME"].strip() or None,
        }
        it = is_in_tags(gem[i], kt[i], cc[i])
        if not it:
            it = {"is_in:country": "CH", "is_in:county": CANTON_NAMES.get(r["COM_CANTON"]),
                  "is_in:city": r["COM_NAME"].strip()}
        # Gemeinde aus dem Verzeichnis hat Vorrang (amtlich), Kanton ebenso
        it["is_in:city"] = r["COM_NAME"].strip()
        it["is_in:county"] = CANTON_NAMES.get(r["COM_CANTON"], it.get("is_in:county"))
        t.update(it)
        b.add_point(g.x, g.y, t)
        n += 1
    log.info("Adresspunkte: %d", n)


NO_ADDR_CLASSES = {"motorway", "motorway_link", "trunk", "steps"}


def link_area_streets(b, pts_lv, streets: list[str], idx, radius: float = 150.0) -> None:
    """Adressen ohne gleichnamige Strasse in der Nähe (Gebiets-/Flurnamen wie „Rüti 1“).

    mkgmap ordnet Hausnummern nur Strassen mit gleichem mkgmap:street zu. Für Adressen, deren
    „Strasse“ ein Gebietsname ist, bekommt die nächste unbenannte Strasse (≤ 150 m) den Tag
    addr:street=<Gebietsname>. Der Default-Style setzt daraus mkgmap:street, ohne dass sich die
    Beschriftung ändert. Je Strasse gewinnt der häufigste Gebietsname.
    """
    names = idx.names
    classes = idx.classes
    ia, ir = idx.tree.query(pts_lv, predicate="dwithin", distance=radius)
    near: dict[int, list[int]] = {}
    for a, r in zip(ia.tolist(), ir.tolist()):
        near.setdefault(a, []).append(r)
    # Kandidaten je Adresse (unbenannte Strassen nach Distanz sortiert)
    pending: dict[str, list[tuple[int, list[int]]]] = {}
    unmatched = linked = 0
    for a, street in enumerate(streets):
        cand = near.get(a, [])
        if any(names[r] == street for r in cand):
            continue
        unmatched += 1
        free = [r for r in cand if names[r] is None and classes[r] not in NO_ADDR_CLASSES]
        if not free:
            continue
        d = shapely.distance(pts_lv[a], idx.geoms[free])
        order = [free[k] for k in np.argsort(d)]
        pending.setdefault(street, []).append((a, order))
    # Gebietsnamen mit vielen Adressen zuerst; eine Strasse bekommt nur einen Gebietsnamen
    claimed: dict[int, str] = {}
    for street, items in sorted(pending.items(), key=lambda kv: -len(kv[1])):
        for _a, order in items:
            for r in order:
                owner = claimed.get(r)
                if owner is None or owner == street:
                    claimed[r] = street
                    linked += 1
                    break
    for r, street in claimed.items():
        for w in idx.ways[r]:
            b.ways[w][1]["addr:street"] = street
    log.info("Adressen ohne gleichnamige Strasse: %d, davon %d einer unbenannten Strasse zugeordnet "
             "(%d Strassenstücke mit addr:street)", unmatched, linked, len(claimed))
