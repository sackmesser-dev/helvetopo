"""Abstands-Tags für den Stil (Wunsch style-typ): `swisstopo:stadtabstand` an Fluss- und Autobahnwegen
nahe einer Stadt, `swisstopo:gipfelabstand` an benannten Pässen.

Problem (Gerätetest 7794-klassen2): Flussnamen und Autobahnschilder verdrängen den Stadtnamen
(„St. Gallen“ fehlt bei 3 km und 8 km). Der Stil blendet deshalb diese Labels in der Nähe einer
Stadt erst bei grösserem Zoom ein (src/style/swisstopo/lines).

- Stadt: Knoten `place=city|town` mit `population>=10000`.
- Wege: `waterway=river|stream|canal|ditch|drain`, `highway=motorway|trunk|motorway_link|trunk_link`
  und Wege mit `swisstopo:shield_autobahn`.
- Wert: kleinster Abstand (ganze Meter) eines Wegknotens zur nächsten Stadt. Gesetzt nur unter 5000 m.
- Lange Wege werden an den Grenzen 1500/2000/3000/4000/5000 m geteilt. Sonst verliert ein Weg,
  der nur kurz nahe an einer Stadt liegt, überall sein Label. Die Teilung liegt am ersten Knoten
  jenseits der Grenze. Neue Wege bekommen IDs über der grössten vorhandenen Weg-ID.

`swisstopo:gipfelabstand` (Entscheid des Benutzers: Ein Pass verdrängt nie einen Gipfel der Klasse 1,
Beispiel Schwägalp Passhöhe neben dem Säntis):
- Pass: Knoten mit `name=*` und `mountain_pass=yes` oder `natural=saddle`, nicht `natural=peak|hill`.
- Wert: Abstand (ganze Meter) zum nächsten `natural=peak|hill` mit `name=*` und `swisstopo:gipfelklasse=1`.
  Gesetzt nur unter 20 000 m.

Beide Schritte laufen auf der fertigen PBF (Einzelbuild in convert.py, Landesbuild nach dem Merge in
build_ch.py). Damit sieht er auch die Städte jenseits einer Kachelgrenze.

    .venv/bin/python -m src.vector.stadtabstand in.osm.pbf out.osm.pbf
"""

from __future__ import annotations

import argparse
import logging
import math
from collections import Counter
from pathlib import Path

import numpy as np
import osmium

log = logging.getLogger("vector")

TAG = "swisstopo:stadtabstand"
PASS_TAG = "swisstopo:gipfelabstand"
PASS_LIMIT = 20000.0
LIMITS = (1500.0, 2000.0, 3000.0, 4000.0, 5000.0)  # Teilungsgrenzen, die letzte ist der Höchstabstand
WATERWAYS = {"river", "stream", "canal", "ditch", "drain"}
HIGHWAYS = {"motorway", "trunk", "motorway_link", "trunk_link"}
MIN_POP = 10000
_KY = 110540.0
_KX = 111320.0 * math.cos(math.radians(46.8))


def is_target(tags) -> bool:
    return (tags.get("waterway") in WATERWAYS or tags.get("highway") in HIGHWAYS
            or "swisstopo:shield_autobahn" in tags)


def is_town(tags) -> bool:
    if tags.get("place") not in ("city", "town"):
        return False
    try:
        return int(float(tags.get("population", "0"))) >= MIN_POP
    except ValueError:
        return False


def is_pass(tags) -> bool:
    return ("name" in tags and (tags.get("mountain_pass") == "yes" or tags.get("natural") == "saddle")
            and tags.get("natural") not in ("peak", "hill"))


def is_main_peak(tags) -> bool:
    return (tags.get("natural") in ("peak", "hill") and "name" in tags
            and tags.get("swisstopo:gipfelklasse") == "1")


def pieces(xy: np.ndarray, towns: np.ndarray):
    """Teilstücke eines Wegs: Liste (erster Knotenindex, letzter Knotenindex, Abstand oder None).

    xy: Knoten in Metern (n×2), towns: Städte in Metern (m×2). Nachbarstücke teilen den Grenzknoten.
    """
    n = len(xy)
    if not len(towns) or n < 2:
        return [(0, n - 1, None)]
    lo, hi = xy.min(axis=0) - LIMITS[-1], xy.max(axis=0) + LIMITS[-1]
    near = towns[np.all((towns >= lo) & (towns <= hi), axis=1)]
    if not len(near):
        return [(0, n - 1, None)]
    d = np.sqrt(((xy[:, None, :] - near[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
    bucket = np.searchsorted(LIMITS, d, side="right")  # 0: <1500 … 5: ≥5000
    # Läufe gleicher Stufe
    cut = np.flatnonzero(bucket[1:] != bucket[:-1]) + 1
    starts = [0, *cut.tolist()]
    ends = [*(c - 1 for c in cut.tolist()), n - 1]
    out = []
    for s, e in zip(starts, ends):
        val = None if bucket[s] >= len(LIMITS) else int(d[s:e + 1].min())
        last = min(e + 1, n - 1)  # Grenzknoten des nächsten Laufs gehört auch zu diesem Stück
        if last == s:  # einzelner Endknoten: an das vorige Stück hängen
            ps, pe, pv = out[-1]
            vals = [v for v in (pv, val) if v is not None]
            out[-1] = (ps, last, min(vals) if vals else None)
            continue
        out.append((s, last, val))
    return out


def _to_m(lon, lat):
    return np.column_stack([np.asarray(lon) * _KX, np.asarray(lat) * _KY])


def process(src: Path, dst: Path) -> Counter:
    stats = Counter()
    town_ll = []
    peak_ll = []
    max_way = 0
    for o in osmium.FileProcessor(str(src), osmium.osm.NODE | osmium.osm.WAY):
        if o.is_node():
            if is_town(o.tags):
                town_ll.append((o.location.lon, o.location.lat))
            if is_main_peak(o.tags):
                peak_ll.append((o.location.lon, o.location.lat))
        else:
            max_way = max(max_way, o.id)
    towns = _to_m(*zip(*town_ll)) if town_ll else np.zeros((0, 2))
    peaks = _to_m(*zip(*peak_ll)) if peak_ll else np.zeros((0, 2))
    stats["staedte"] = len(towns)
    stats["gipfel_klasse1"] = len(peaks)
    next_id = max_way + 1
    pending = []

    tmp = Path(dst).with_suffix(".tmp.pbf")
    if tmp.exists():
        tmp.unlink()
    w = osmium.SimpleWriter(str(tmp))
    try:
        fp = osmium.FileProcessor(str(src)).with_locations()
        for o in fp:
            if o.is_node():
                if len(peaks) and is_pass(o.tags):
                    xy = _to_m([o.location.lon], [o.location.lat])[0]
                    d = float(np.sqrt(((peaks - xy) ** 2).sum(axis=1)).min())
                    if d < PASS_LIMIT:
                        tags = {t.k: t.v for t in o.tags}
                        tags[PASS_TAG] = str(int(d))
                        w.add_node(o.replace(tags=tags))
                        stats["paesse"] += 1
                        continue
                w.add_node(o)
                continue
            if o.is_relation():
                for p in pending:
                    w.add_way(p)
                pending.clear()
                w.add_relation(o)
                continue
            if not is_target(o.tags) or not len(towns):
                w.add_way(o)
                continue
            refs = [nd.ref for nd in o.nodes]
            locs = [nd.location for nd in o.nodes]
            if not all(l.valid() for l in locs):
                w.add_way(o)
                stats["ohne_koordinaten"] += 1
                continue
            xy = _to_m([l.lon for l in locs], [l.lat for l in locs])
            parts = pieces(xy, towns)
            if len(parts) == 1 and parts[0][2] is None:
                w.add_way(o)
                continue
            base = {t.k: t.v for t in o.tags}
            base.pop(TAG, None)
            for i, (s, e, v) in enumerate(parts):
                tags = dict(base)
                if v is not None:
                    tags[TAG] = str(v)
                    stats["markiert"] += 1
                way = osmium.osm.mutable.Way(id=o.id if i == 0 else next_id, version=1,
                                             nodes=refs[s:e + 1], tags=tags)
                if i == 0:
                    w.add_way(way)
                else:
                    next_id += 1
                    pending.append(way)
                    stats["neue_wege"] += 1
        for p in pending:
            w.add_way(p)
    finally:
        w.close()
    tmp.replace(dst)
    return stats


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("dst")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    log.info("stadtabstand: %s", dict(process(Path(a.src), Path(a.dst))))


if __name__ == "__main__":
    main()
