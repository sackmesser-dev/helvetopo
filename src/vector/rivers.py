"""Flussordnung aus dem swissTLM3D-Gewässernetz (ohne Fremdquelle).

Je Abschnitt von tlm_gewaesser_fliessgewaesser:
- Strahler-Ordnung: Quellabschnitte 1; an einem Zusammenfluss die grösste Ordnung der Zuflüsse,
  +1 wenn mindestens zwei Zuflüsse diese Ordnung haben.
- Gewässerlänge oberhalb (km, inkl. des Abschnitts selbst): Ersatz für das Einzugsgebiet, das
  swissTLM3D nicht enthält. An Verzweigungen (Flussarme, Bisses) wird die Länge auf die Abflüsse
  aufgeteilt, damit sie sich bei Mehrfachverzweigungen nicht aufschaukelt.
- Gewässerklasse 1–6 aus der Länge oberhalb (für Stil: Dicke und Zoomstufe).

Arme desselben Gewässers (gleiche GEWISS-Nr.), die sich wieder vereinigen, erhöhen die Ordnung nicht.

Grundlage: Die Abschnitte sind in Fliessrichtung digitalisiert (geprüft: 99,98 % der Abschnitte mit
Höhenunterschied fallen vom ersten zum letzten Punkt) und an Zusammenflüssen verknotet. Seeachsen
verbinden Zu- und Abfluss durch Seen. Druckleitungen und -stollen sowie Bisses/Suonen (Wasserfassungen,
Bewässerung) zählen nicht als natürliches Netz: Sie bekommen keine Ordnung und reichen keine weiter.

Das Netz wird landesweit gerechnet (sonst wäre die Ordnung an Gebiets- und Kachelgrenzen falsch) und
als CSV zwischengespeichert: work/vector/cache/fliessgewaesser_ordnung.csv (uuid → Werte).
Grenzen: Zuflüsse aus dem Ausland fehlen (z. B. Doubs aus Frankreich), dort ist die Ordnung zu tief.

    .venv/bin/python -m src.vector.rivers     # Cache neu rechnen und Statistik ausgeben
"""

from __future__ import annotations

import csv
import logging
import os
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pyogrio
import shapely

from .common import TLM_GPKG

log = logging.getLogger("vector")

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "work" / "vector" / "cache" / "fliessgewaesser_ordnung.csv"
NATURAL = {"Fliessgewaesser", "Seeachse", "Trockenrinne"}
# Gewässerklasse aus der Gewässerlänge oberhalb (km). swissTLM3D hat etwa 2,5 km Gewässer je km²
# Einzugsgebiet, die Grenzen entsprechen also grob 1 / 6 / 25 / 120 / 600 km² Einzugsgebiet.
# Beispiele an der Mündung: 4 Steinach, Goldach; 5 Glatt, Necker, Urnäsch, Sitter; 6 Thur, Reuss.
CLASS_KM = [(3.0, 1), (15.0, 2), (60.0, 3), (300.0, 4), (1500.0, 5)]


def water_class(km: float) -> int:
    for lim, c in CLASS_KM:
        if km < lim:
            return c
    return 6


def _key(xy: np.ndarray) -> np.ndarray:
    """Knoten-Schlüssel aus LV95 (auf 5 cm gerundet)."""
    q = np.round(xy / 0.05).astype(np.int64)
    return q[:, 0] * 100_000_000 + q[:, 1]


def compute() -> dict[str, tuple[int, float, int]]:
    df = pyogrio.read_dataframe(TLM_GPKG, layer="tlm_gewaesser_fliessgewaesser", columns=["uuid", "objektart", "gewiss_nr"])
    df = df[df["objektart"].isin(NATURAL)].reset_index(drop=True)
    g = shapely.force_2d(df.geometry.values)
    n = len(g)
    start = _key(shapely.get_coordinates(shapely.get_point(g, 0)))
    end = _key(shapely.get_coordinates(shapely.get_point(g, -1)))
    length = shapely.length(g) / 1000.0
    # Gewässer-Identität: Arme desselben Gewässers (gleiche GEWISS-Nr.), die sich wieder vereinigen,
    # erhöhen die Ordnung nicht (sonst steigt sie in verflochtenen Strecken auf über 80)
    gw = df["gewiss_nr"].tolist()
    ident = [str(int(float(x))) if x is not None and x == x else f"#{i}" for i, x in enumerate(gw)]
    out_edges = defaultdict(list)   # Knoten → abgehende Abschnitte
    in_edges = defaultdict(list)    # Knoten → ankommende Abschnitte
    for i in range(n):
        out_edges[start[i]].append(i)
        in_edges[end[i]].append(i)

    order = np.zeros(n, dtype=np.int32)
    up = np.zeros(n, dtype=np.float64)
    # Kahn-Sortierung über Knoten: ein Abschnitt ist fertig, wenn alle Zuflüsse seines Startknotens fertig sind
    pending = {k: len(v) for k, v in in_edges.items()}
    q = deque(k for k in out_edges if pending.get(k, 0) == 0)
    done_nodes = set()

    # Nebenarm: Abfluss einer Verzweigung ausser dem Hauptarm, und alles unterhalb davon bis zum
    # nächsten Knoten mit einem Hauptzufluss. Nebenarme zählen am Wiedereintritt nicht als Zufluss.
    secondary = np.zeros(n, dtype=bool)

    def settle(node):
        ins = in_edges.get(node, [])
        prim = [j for j in ins if not secondary[j]] or ins
        if ins:
            best: dict = {}
            for j in prim:
                best[ident[j]] = max(best.get(ident[j], 0), order[j])
            o = list(best.values())
            m = max(o)
            node_order = m + 1 if o.count(m) >= 2 else m
            node_up = sum(up[j] for j in ins)
            main_ident = ident[max(prim, key=lambda j: (order[j], up[j]))]
            node_secondary = all(secondary[j] for j in ins)
        else:
            node_order, node_up, main_ident, node_secondary = 1, 0.0, None, False
        outs = out_edges.get(node, [])
        share = node_up / len(outs) if outs else 0.0
        main = None
        if len(outs) > 1:
            same = [j for j in outs if ident[j] == main_ident]
            main = max(same or outs, key=lambda j: length[j])
        for j in outs:
            order[j] = max(node_order, 1)
            up[j] = share + length[j]
            secondary[j] = node_secondary or (main is not None and j != main)
        return outs

    while True:
        while q:
            node = q.popleft()
            if node in done_nodes:
                continue
            done_nodes.add(node)
            for j in settle(node):
                e = end[j]
                pending[e] -= 1
                if pending[e] == 0:
                    q.append(e)
        # Zyklen (verflochtene Arme, Digitalisierfehler): Knoten mit den meisten fertigen Zuflüssen
        # trotzdem abschliessen, unfertige Zuflüsse zählen als 0
        rest = [k for k, v in pending.items() if v > 0 and k not in done_nodes]
        if not rest:
            break
        k = max(rest, key=lambda r: len(in_edges[r]) - pending[r])
        pending[k] = 0
        q.append(k)
    uu = [str(u).strip("{}").upper() for u in df["uuid"]]
    return {u: (int(order[i]), float(up[i]), water_class(up[i])) for i, u in enumerate(uu)}


def write_cache(res: dict, path: Path = CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["uuid", "strahler", "laenge_oberhalb_km", "klasse"])
        for u, (o, km, c) in res.items():
            w.writerow([u, o, f"{km:.2f}", c])
    tmp.replace(path)


def load(path: Path = CACHE) -> dict[str, tuple[int, float, int]]:
    """Ordnung je TLM-uuid; rechnet und speichert den Cache, falls er fehlt oder älter als das GPKG ist."""
    if not path.exists() or path.stat().st_mtime < Path(TLM_GPKG).stat().st_mtime:
        log.info("Flussordnung: rechne landesweit (Cache %s)", path)
        write_cache(compute(), path)
    res = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            res[r["uuid"]] = (int(r["strahler"]), float(r["laenge_oberhalb_km"]), int(r["klasse"]))
    return res


def tags(res: dict, uuid: str) -> dict:
    v = res.get(str(uuid).strip("{}").upper())
    if v is None:
        return {}
    return {"swisstopo:strahler": str(v[0]), "swisstopo:laenge_oberhalb_km": f"{v[1]:.1f}",
            "swisstopo:gewaesserklasse": str(v[2])}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    import time
    t0 = time.time()
    res = compute()
    write_cache(res)
    o = np.array([v[0] for v in res.values()])
    c = np.array([v[2] for v in res.values()])
    log.info("fertig in %.0f s: %d Abschnitte", time.time() - t0, len(res))
    log.info("Strahler: %s", {int(k): int((o == k).sum()) for k in np.unique(o)})
    log.info("Klasse: %s", {int(k): int((c == k).sum()) for k in np.unique(c)})
