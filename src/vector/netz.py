"""Netzkonnektivität je Zoomstufe: swisstopo:netz_res (Wunsch style-typ, Review „Strassen in der Luft“).

Der Stil wählt Strassen je Auflösung nach Klasse. Dadurch hängen Stücke in der Luft: Eine 4-m-Strasse
mit Hartbelag kommt ab 21, ihr Anschluss mit Naturbelag erst ab 22. Dieses Modul rechnet für jeden
Strassenabschnitt die tiefste Auflösung, ab der er gezeichnet werden soll, so dass jede sichtbare
Netzkomponente an das übergeordnete Netz anschliesst oder für sich gross genug ist.

Basisstufe je Klasse (wie der Stil ohne Tag zeichnet):
- Anker (immer sichtbar, kein Tag): Autobahn, Autostrasse, Aus-/Einfahrt, Zufahrt, Raststätte,
  Verbindung und alles mit Verkehrsbedeutung (ausser 2m Weg).
- 19: Kantonsstrassen (eigentuemer=Kanton) 4m–10m ohne Verkehrsbedeutung.
- 21: 6m/8m/10m Strasse, 4m und 3m Strasse mit Hartbelag.
- 22: Platz, Dienstzufahrt, Strassen mit Naturbelag, 2m/1m Weg, Wegfragmente, Markierte Spur.
- ohne Tag und ausserhalb des Netzes: Treppen, Klettersteige, Fähren, Autozug.

Je r = 19 … 22 aufsteigend:
1. Sichtbar sind Anker, Basis ≤ r und alles, was in r−1 sichtbar war. Komponenten über gemeinsame Endpunkte.
2. Verankert ist eine Komponente mit Anker, mit mehr als A_r Gesamtlänge oder am Rand des Rechengebiets
   (Kachelgrenze: dort ist das Netz abgeschnitten, also nicht beurteilbar).
3. Sonst kürzester Pfad über noch unsichtbare Abschnitte zu einer verankerten Komponente (in 19–21 nur
   Strassen, in 22 auch Wege). Ist er ≤ P_r, werden seine Abschnitte für r hochgestuft.
4. Sonst wird die Komponente in r versteckt (ausser in 22 reine Wegfragment-Komponenten).
Verbindungen: gemeinsame Endpunkte (5 cm), Endpunkte ≤ 0,5 m neben einem anderen Abschnitt (T-Anschluss
ohne Knoten) und in 22 Treppen und Klettersteige (selbst ohne Tag).
netz_res = kleinste sichtbare Stufe, nie sichtbar bis 22 → 23.
"""

from __future__ import annotations

import heapq
import logging
from collections import Counter, defaultdict

import numpy as np
import shapely

log = logging.getLogger("vector")

LEVELS = (19, 20, 21, 22)
ANCHOR_M = {19: 5000.0, 20: 5000.0, 21: 2000.0, 22: 1000.0}   # A_r: Mindestlänge einer freien Komponente
PATH_M = {19: 800.0, 20: 800.0, 21: 400.0, 22: 250.0}         # P_r: längster Lückenschluss

ANCHOR_OA = {"Autobahn", "Autostrasse", "Ausfahrt", "Einfahrt", "Zufahrt", "Raststaette", "Verbindung"}
BIG_ROADS = {"6m Strasse", "8m Strasse", "10m Strasse"}
CANTON_ROADS = {"4m Strasse", "6m Strasse", "8m Strasse", "10m Strasse"}
LEVEL22 = {"Platz", "Dienstzufahrt"}
WAYS = {"2m Weg", "1m Weg", "1m Wegfragment", "2m Wegfragment", "Markierte Spur"}
STAIRS = {"Treppe", "Bruecke mit Treppe", "Unterfuehrung mit Treppe"}
ANCHOR, NONE = 0, -1


def base_level(r: dict) -> int:
    """Basisstufe eines Abschnitts (ANCHOR, 19, 21, 22) oder NONE (nicht im Netz)."""
    oa = r.get("objektart")
    if r.get("kunstbaute") in STAIRS or oa in ("Klettersteig", "Faehre", "Autozug"):
        return NONE
    if oa in ANCHOR_OA or (r.get("verkehrsbedeutung") and oa != "2m Weg"):
        return ANCHOR
    natur = r.get("belagsart") == "Natur"
    if oa in CANTON_ROADS and r.get("eigentuemer") == "Kanton":
        return 19
    if oa in BIG_ROADS or (oa in ("4m Strasse", "3m Strasse") and not natur):
        return 21
    if oa in LEVEL22 or oa in WAYS or oa in ("4m Strasse", "3m Strasse"):
        return 22
    return NONE


def _key(xy: np.ndarray) -> np.ndarray:
    q = np.round(xy / 0.05).astype(np.int64)
    return q[:, 0] * 100_000_000 + q[:, 1]


class _DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        p = self.p
        p.setdefault(x, x)
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def compute(recs: list[dict], geoms_lv95: np.ndarray, bbox=None) -> tuple[np.ndarray, dict]:
    """netz_res je Abschnitt (0 = Anker/ohne Tag, 19–23) und Statistik je Stufe.

    bbox: LV95-Rechteck des gelesenen Gebiets; Abschnitte, die seinen Rand schneiden, verankern ihre
    Komponente (das Netz geht ausserhalb weiter).
    """
    n = len(recs)
    base = np.array([base_level(r) for r in recs], dtype=np.int32)
    is_way = np.array([r.get("objektart") in WAYS for r in recs], dtype=bool)
    frag = np.array([(r.get("objektart") or "").endswith("Wegfragment") for r in recs], dtype=bool)
    length = shapely.length(geoms_lv95)
    u = _key(shapely.get_coordinates(shapely.get_point(geoms_lv95, 0)))
    v = _key(shapely.get_coordinates(shapely.get_point(geoms_lv95, -1)))
    edge = np.zeros(n, dtype=bool)
    if bbox is not None:
        inner = shapely.box(bbox[0] + 1, bbox[1] + 1, bbox[2] - 1, bbox[3] - 1)
        edge = ~shapely.within(geoms_lv95, inner)
    # Treppen und Klettersteige verbinden in 22 Wege (werden selbst nicht getaggt)
    link = np.array([r.get("kunstbaute") in STAIRS or r.get("objektart") == "Klettersteig" for r in recs],
                    dtype=bool)
    net = np.where((base != NONE) | link)[0]
    adj = defaultdict(list)   # Knoten → [(Abschnitt, Nachbarknoten, Kosten)]
    for i in net.tolist():
        adj[u[i]].append((i, v[i], length[i]))
        adj[v[i]].append((i, u[i], length[i]))
    # Anschlüsse mitten auf einem Abschnitt (T-Knoten ohne gemeinsamen Endpunkt, ≤ 0,5 m):
    # Endpunkt x hängt an Abschnitt j, Kosten je halbe Länge von j bis zu dessen Enden
    tee = defaultdict(list)   # Abschnitt j → angehängte Knoten
    if len(net):
        gn = geoms_lv95[net]
        ends = np.concatenate([shapely.get_point(gn, 0), shapely.get_point(gn, -1)])
        keys = np.concatenate([u[net], v[net]])
        own = np.concatenate([net, net])
        pi, gi = shapely.STRtree(gn).query(ends, predicate="dwithin", distance=0.5)
        for a, b in zip(pi.tolist(), gi.tolist()):
            j = int(net[b])
            x = int(keys[a])
            if j == own[a] or x == u[j] or x == v[j]:
                continue
            tee[j].append(x)
            h = length[j] / 2
            adj[x].append((j, u[j], h))
            adj[x].append((j, v[j], h))
            adj[u[j]].append((j, x, h))
            adj[v[j]].append((j, x, h))

    res = np.full(n, 0, dtype=np.int32)
    visible = base == ANCHOR
    first = np.full(n, 99, dtype=np.int32)
    stats = {}
    for r in LEVELS:
        vis = visible | ((base != NONE) & (base != ANCHOR) & (base <= r))
        dsu = _DSU()
        idx = np.where(vis)[0]
        for i in idx.tolist():
            dsu.union(u[i], v[i])
            for x in tee.get(i, ()):
                dsu.union(x, u[i])
        comp_len = Counter()
        comp_anchor = set()
        comp_edges = defaultdict(list)
        for i in idx.tolist():
            c = dsu.find(u[i])
            comp_len[c] += length[i]
            comp_edges[c].append(i)
            if base[i] == ANCHOR or edge[i]:
                comp_anchor.add(c)
        anchored = {c for c in comp_edges if c in comp_anchor or comp_len[c] > ANCHOR_M[r]}
        nodes_of = defaultdict(set)   # Komponente → Knoten (inkl. T-Anschlüsse)
        for x in list(dsu.p):
            nodes_of[dsu.find(x)].add(x)
        anchored_nodes = set()
        for c in anchored:
            anchored_nodes |= nodes_of[c]
        upgraded = hidden = hidden_km = up_km = 0
        new_vis = vis.copy()
        loose = sorted((c for c in comp_edges if c not in anchored), key=lambda c: -comp_len[c])
        for c in loose:
            starts = nodes_of[c]
            if starts & anchored_nodes:   # durch eine frühere Hochstufung schon angeschlossen
                anchored_nodes |= starts
                continue
            path = _shortest_link(starts, anchored_nodes, adj, vis, is_way | (link & (r < 22)), r)
            if path is not None:
                for i in path:
                    new_vis[i] = not link[i] or base[i] != NONE
                    anchored_nodes.add(u[i])
                    anchored_nodes.add(v[i])
                anchored_nodes |= starts
                upgraded += len(path)
                up_km += sum(length[i] for i in path) / 1000
            elif r == 22 and all(frag[i] for i in comp_edges[c]):
                pass   # Wegfragmente sind per Definition Einzelstücke (LK zeigt sie), nicht verstecken
            else:
                for i in comp_edges[c]:
                    new_vis[i] = False
                hidden += len(comp_edges[c])
                hidden_km += comp_len[c] / 1000
        visible = new_vis
        first[(first == 99) & visible] = r
        stats[r] = {"hochgestuft": upgraded, "hochgestuft_km": round(float(up_km), 1),
                    "versteckt": hidden, "versteckt_km": round(float(hidden_km), 1)}
    tag = (base != ANCHOR) & (base != NONE)
    res[tag] = np.where(first[tag] == 99, 23, first[tag])
    return res, stats


def _shortest_link(starts, targets, adj, vis, blocked, r):
    """Kürzester Pfad (Abschnittsliste) über unsichtbare Abschnitte von starts zu targets, ≤ PATH_M[r]."""
    limit = PATH_M[r]
    dist = {s: 0.0 for s in starts}
    prev = {}
    heap = [(0.0, s) for s in starts]
    heapq.heapify(heap)
    while heap:
        d, x = heapq.heappop(heap)
        if d > dist.get(x, np.inf):
            continue
        if x in targets:
            path = []
            while x in prev:
                i, x = prev[x]
                path.append(i)
            return path
        for i, y, w in adj[x]:
            if vis[i] or (r < 22 and blocked[i]):
                continue
            nd = d + w
            if nd <= limit and nd < dist.get(y, np.inf):
                dist[y] = nd
                prev[y] = (i, x)
                heapq.heappush(heap, (nd, y))
    return None


def add_tags(all_tags: list[dict], recs: list[dict], geoms_lv95: np.ndarray, bbox=None) -> dict:
    res, stats = compute(recs, geoms_lv95, bbox)
    for t, x in zip(all_tags, res.tolist()):
        if x:
            t["swisstopo:netz_res"] = str(x)
    log.info("Netz je Stufe: %s", stats)
    return stats
