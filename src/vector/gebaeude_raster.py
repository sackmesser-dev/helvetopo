"""Gebäude vor dem Runden auf das Garmin-Raster ausrichten (Wunsch style-typ, Befund Niederuzwil, Friedeckstrasse).

Problem: mkgmap rundet jeden Punkt auf das Raster der Auflösung 24 (360°/2^24, in der Schweiz ca.
1,6 m × 2,4 m). Die rechtwinkligen TLM-Grundrisse (Abweichung im Median 0,1°) bekommen dabei schiefe
Ecken (Median 4,8°, 10 % über 22°). Die Gebäude wirken unruhig.

Abhilfe: Je Gruppe sich berührender Gebäude eine gemeinsame kleine Drehung um den Schwerpunkt
(±3°) und eine Verschiebung um Bruchteile einer Rastereinheit (±0,5). Gewählt wird die Lage, bei der
die gerundeten Ecken ihre Originalwinkel am besten behalten. Eine Strafe auf die Bewegung jeder Ecke
(höchstens MAX_DISP_M) hält die Gebäude nahe an der Originallage, auch in grossen Gruppen. Die
Koordinaten werden schon gerundet geschrieben.

Puffer (Standard aus): Mit BUFFER_M > 0 wächst jeder Grundriss vorher um BUFFER_M nach aussen. Schmale
Schlitze zwischen Nachbarteilen schliessen sich dann beim Runden, aber die Häuser werden dicker.
Gemeinsame Drehung je Gruppe: Aneinandergebaute Häuser behalten ihre gemeinsamen Wände (einzeln
ausgerichtet entstehen Kerben zwischen den Teilen).

Suche: grob (13 Drehungen × 16 Verschiebungen), danach fein um das beste Ergebnis (27 Varianten).
Alle Gruppen werden gleichzeitig gerechnet (numpy über alle Ecken).

Gruppe: Gebäude (alle building=*, auch Multipolygone), deren (gepufferte) Flächen sich überlappen,
ineinander liegen oder weniger als TOUCH_M voneinander entfernt sind.

Knoten, die ein Gebäude mit einer Netzlinie teilt (Strasse, Bahn, Gewässer, Mauer), bleiben an ihrem Ort.
Das Gebäude bekommt dort einen eigenen Knoten. Mit Flächen (Areale, Landnutzung) geteilte Knoten
verschieben sich mit dem Gebäude. Verschobene Knoten bekommen im Kachelmodus eine
Kachel-ID (nicht mehr die Koordinaten-ID), weil zwei Ecken auf denselben Rasterpunkt fallen können.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import shapely

from .common import COORD_SCALE

log = logging.getLogger("vector")

UNIT = 360.0 / (1 << 24)          # Rastereinheit der Auflösung 24 in Grad
M_PER_DEG = 111_320.0
MAX_ROT = 3.0                      # Grad
# Puffer: Mit BUFFER_M > 0 wächst jeder Grundriss (geschlossener Weg) vor dem Ausrichten um BUFFER_M nach
# aussen (spitze Ecken). Schlitze unter 2·BUFFER_M zwischen Nachbarteilen schliessen sich.
# Standard 0 (Gerätetest GPSMAP 67, 2026-11-08): Mit 0,4 m wächst die sichtbare Gebäudefläche im Testgebiet
# um 10,4 %, Dörfer und Städte werden zu schwarz. Ohne Puffer +0,5 %, mit 0,15 m +4,2 %. Kein Haus
# verschwindet ohne Puffer. Der Benutzer wählte die Variante ohne Puffer.
BUFFER_M = 0.0
# „berühren“ (nach dem Puffer): Flächen überlappen, liegen ineinander oder sind < TOUCH_M entfernt. Mit Puffer
# heisst das: Die Originale liegen weniger als 2·BUFFER_M auseinander.
TOUCH_M = 0.05
# Knoten, die ein Gebäude mit einem Weg dieser Arten teilt, bleiben stehen (Netz, Mauern). An Flächen
# (Areale, Landnutzung) verschiebt sich der gemeinsame Knoten mit dem Gebäude, sonst entstehen Keile.
# T-Knoten (Ecke nahe an der Wand eines Nachbarn → gemeinsamer Knoten): aus. Gerundet liegen sie fast nie
# auf der gerundeten Wand, die Wände bekommen Knicke (Test v3: 716 statt 231 Knicke 3–20°). 0 = aus.
T_NODE_M = 0.0
FIXED_KEYS = ("highway", "railway", "waterway", "aerialway", "barrier", "power", "route")
DUP_PENALTY = 1e6                  # je Ecke, die beim Runden mit der vorigen zusammenfällt
# Lagetreue: Drehung und Verschiebung bewegen jede Ecke um d (m, vor dem Runden). Kosten je Ecke DISP_PENALTY · d².
# Bei grossen Gruppen bewegt schon eine kleine Drehung die äusseren Ecken weit (Hebelarm), darum zählt
# die Bewegung der Ecken und nicht der Drehwinkel. Mehr als MAX_DISP_M ist nicht erlaubt.
DISP_PENALTY = 4.0
MAX_DISP_M = 2.0
COARSE_ROT = np.arange(-MAX_ROT, MAX_ROT + 1e-9, 0.5)
COARSE_SHIFT = np.arange(-0.5, 0.5, 0.25)
FINE_ROT = (-0.25, 0.0, 0.25)
FINE_SHIFT = (-0.125, 0.0, 0.125)
FULL_ROT = np.arange(-MAX_ROT, MAX_ROT + 1e-9, 0.25)
FULL_SHIFT = np.arange(-0.5, 0.5, 0.125)


def _is_building(tags: dict) -> bool:
    v = tags.get("building")
    return v is not None and v != "no"


class _Rings:
    """Alle Gebäuderinge als flache Arrays (eine Zeile je Ecke)."""

    def __init__(self, b, ring_ways, ring_item):
        refs, ring_of, closed = [], [], []
        for r, wi in enumerate(ring_ways):
            nodes = b.ways[wi][0]
            cl = len(nodes) > 3 and nodes[0] == nodes[-1]
            nodes = nodes[:-1] if cl else nodes
            refs.extend(nodes)
            ring_of.extend([r] * len(nodes))
            closed.append(cl)
        self.ref = np.array(refs, dtype=np.int64)            # interner Knotenindex (ab 1)
        self.ring = np.array(ring_of, dtype=np.int64)
        self.item = np.asarray(ring_item, dtype=np.int64)[self.ring]
        n = len(self.ref)
        start = np.r_[0, np.flatnonzero(np.diff(self.ring)) + 1]
        end = np.r_[start[1:], n] - 1
        first = np.repeat(start, end - start + 1)
        last = np.repeat(end, end - start + 1)
        idx = np.arange(n)
        self.prev = np.where(idx == first, last, idx - 1)
        self.next = np.where(idx == last, first, idx + 1)
        cl = np.asarray(closed)[self.ring]
        # offene Ringe (geteilte Multipolygon-Mitglieder): Endpunkte haben keinen Winkel
        self.end = ~cl & ((idx == first) | (idx == last))


def _angles(x, y, prev, nxt):
    ax, ay = x[prev] - x, y[prev] - y
    bx, by = x[nxt] - x, y[nxt] - y
    la, lb = np.hypot(ax, ay), np.hypot(bx, by)
    ok = (la > 1e-9) & (lb > 1e-9)
    cos = np.where(ok, (ax * bx + ay * by) / np.where(ok, la * lb, 1.0), 1.0)
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))), ok


def _buffer_ways(b, ring_ways, member_ways) -> int:
    """Geschlossene Gebäudewege (keine Multipolygon-Mitglieder) um BUFFER_M nach aussen puffern.
    Jeder gepufferte Ring bekommt eigene Knoten. Die alten Knoten schreibt der Builder nur noch, wenn
    ein anderer Weg sie braucht oder sie Tags haben."""
    if BUFFER_M <= 0:
        return 0
    lon = np.asarray(b.node_lon, dtype=np.float64) / COORD_SCALE
    lat = np.asarray(b.node_lat, dtype=np.float64) / COORD_SCALE
    todo = [wi for wi in ring_ways if wi not in member_ways]
    if not todo:
        return 0
    first = np.array([b.ways[wi][0][0] for wi in todo])
    kx = M_PER_DEG * math.cos(math.radians(float(lat[first - 1].mean())))
    polys = []
    for wi in todo:
        r = np.asarray(b.ways[wi][0]) - 1
        polys.append(shapely.polygons(np.column_stack([lon[r] * kx, lat[r] * M_PER_DEG])))
    polys = np.array(polys, dtype=object)
    bad = ~shapely.is_valid(polys)
    polys[bad] = shapely.make_valid(polys[bad])
    grown = shapely.buffer(polys, BUFFER_M, join_style="mitre", mitre_limit=2.0)
    n = 0
    for wi, g, p0 in zip(todo, grown, polys):
        if g is None or g.is_empty or g.geom_type != "Polygon":
            continue
        ext = shapely.get_coordinates(g.exterior)
        # gleiche Umlaufrichtung wie das Original (die Fläche bleibt dieselbe, die Richtung ist egal)
        refs = [b._new_node(int(round(x / kx * COORD_SCALE)), int(round(y / M_PER_DEG * COORD_SCALE)),
                            shared=False) for x, y in ext[:-1]]
        refs.append(refs[0])
        b.ways[wi] = (refs, b.ways[wi][1])
        n += 1
    return n


def _insert_t_nodes(b, ring_ways) -> int:
    """T-Stellen schliessen: Liegt die Ecke eines Gebäudes auf der Wand eines anderen (ohne gemeinsamen
    Knoten), bekommt die Wand diesen Knoten. Sonst runden beide Teile verschieden, und es entsteht ein Keil."""
    if T_NODE_M <= 0:
        return 0
    lon = np.asarray(b.node_lon, dtype=np.float64) / COORD_SCALE
    lat = np.asarray(b.node_lat, dtype=np.float64) / COORD_SCALE
    nodes = np.unique(np.concatenate([np.asarray(b.ways[wi][0]) for wi in ring_ways]))
    if not len(nodes):
        return 0
    kx = M_PER_DEG * math.cos(math.radians(float(lat[nodes - 1].mean())))
    pts = shapely.points(lon[nodes - 1] * kx, lat[nodes - 1] * M_PER_DEG)
    lines = np.array([shapely.linestrings(np.column_stack([lon[np.asarray(b.ways[wi][0]) - 1] * kx,
                                                           lat[np.asarray(b.ways[wi][0]) - 1] * M_PER_DEG]))
                      for wi in ring_ways], dtype=object)
    pi, li = shapely.STRtree(lines).query(pts, predicate="dwithin", distance=T_NODE_M)
    todo = {}
    for p, l in zip(pi.tolist(), li.tolist()):
        nid = int(nodes[p])
        wi = ring_ways[l]
        refs = b.ways[wi][0]
        if nid in refs:
            continue
        # Wandstück mit dem kleinsten Abstand; Endpunkte zählen nicht (dort liegt schon eine Ecke)
        xy = np.column_stack([lon[np.asarray(refs) - 1] * kx, lat[np.asarray(refs) - 1] * M_PER_DEG])
        a, c = xy[:-1], xy[1:]
        q = np.array([lon[nid - 1] * kx, lat[nid - 1] * M_PER_DEG])
        d = c - a
        L2 = np.maximum((d * d).sum(1), 1e-12)
        t = ((q - a) * d).sum(1) / L2
        dist = np.hypot(*(a + np.clip(t, 0, 1)[:, None] * d - q).T)
        k = int(np.argmin(dist))
        if dist[k] < T_NODE_M and 1e-6 < t[k] < 1 - 1e-6:
            todo.setdefault(wi, []).append((k, float(t[k]), nid))
    n = 0
    for wi, ins in todo.items():
        refs, tags = b.ways[wi]
        out = list(refs)
        for k, t, nid in sorted(ins, key=lambda x: (x[0], x[1]), reverse=True):
            if nid not in out:
                out.insert(k + 1, nid)
                n += 1
        b.ways[wi] = (out, tags)
    return n


def _groups(b, items_rings, ring_ways):
    """Zusammenhangskomponenten der Gebäude (Flächen mit Abstand < TOUCH_M)."""
    n_items = len(items_rings)
    parent = np.arange(n_items)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, c = find(i), find(j)
        if a != c:
            parent[max(a, c)] = min(a, c)

    ring_item = np.empty(len(ring_ways), dtype=np.int64)
    for it, rs in enumerate(items_rings):
        ring_item[rs] = it
    lon = np.asarray(b.node_lon, dtype=np.float64) / COORD_SCALE
    lat = np.asarray(b.node_lat, dtype=np.float64) / COORD_SCALE
    # Flächen statt Ränder: Ein Dach über einem Gebäude oder ein überlappender Teil berührt den Rand nicht
    geoms = []
    for wi in ring_ways:
        nodes = np.asarray(b.ways[wi][0]) - 1
        xy = np.column_stack([lon[nodes], lat[nodes]])
        if len(nodes) >= 4 and nodes[0] == nodes[-1]:
            g = shapely.polygons(xy)
            if not shapely.is_valid(g):
                g = shapely.make_valid(g)
        else:
            g = shapely.linestrings(xy)
        geoms.append(g)
    geoms = np.array(geoms, dtype=object)
    tree = shapely.STRtree(geoms)
    lat0 = float(np.mean(lat[np.asarray(b.ways[ring_ways[0]][0]) - 1]))
    a, c = tree.query(geoms, predicate="dwithin", distance=TOUCH_M / (M_PER_DEG * math.cos(math.radians(lat0))))
    for i, j in zip(ring_item[a].tolist(), ring_item[c].tolist()):
        if i != j:
            union(i, j)
    root = np.array([find(i) for i in range(n_items)])
    _, gid = np.unique(root, return_inverse=True)
    return gid, ring_item


class _Problem:
    def __init__(self, b, R: _Rings, item_group, n_groups):
        self.g = np.asarray(item_group)[R.item]
        self.G = n_groups
        lon_u = np.asarray(b.node_lon, dtype=np.float64)[R.ref - 1] / COORD_SCALE / UNIT
        lat_u = np.asarray(b.node_lat, dtype=np.float64)[R.ref - 1] / COORD_SCALE / UNIT
        cnt = np.bincount(self.g, minlength=n_groups)
        self.cu = np.bincount(self.g, lon_u, n_groups) / cnt
        self.cv = np.bincount(self.g, lat_u, n_groups) / cnt
        lat0 = self.cv * UNIT
        self.sx = (UNIT * M_PER_DEG * np.cos(np.radians(lat0)))   # m je Einheit, je Gruppe
        self.sy = UNIT * M_PER_DEG
        sxv = self.sx[self.g]
        self.x = (lon_u - self.cu[self.g]) * sxv                 # m, relativ zum Schwerpunkt
        self.y = (lat_u - self.cv[self.g]) * self.sy
        self.prev, self.next, self.end = R.prev, R.next, R.end
        self.ang0, ok0 = _angles(self.x, self.y, self.prev, self.next)
        self.ok0 = ok0 & ~self.end

    def place(self, th, du, dv):
        """Gerundete Rasterkoordinaten (ganze Einheiten) für Drehung th (Grad) und Verschiebung je Gruppe."""
        t = np.radians(th)[self.g]
        c, s = np.cos(t), np.sin(t)
        xr = c * self.x - s * self.y
        yr = s * self.x + c * self.y
        u = np.round(xr / self.sx[self.g] + self.cu[self.g] + du[self.g])
        v = np.round(yr / self.sy + self.cv[self.g] + dv[self.g])
        return u, v

    def cost(self, th, du, dv):
        u, v = self.place(th, du, dv)
        X = u * self.sx[self.g]
        Y = v * self.sy
        ang, ok = _angles(X, Y, self.prev, self.next)
        m = ok & self.ok0
        err = np.where(m, (ang - self.ang0) ** 2, 0.0)
        dup = (u == u[self.prev]) & (v == v[self.prev]) & ~self.end
        d2 = self.disp2(th, du, dv)
        c = np.bincount(self.g, err + DUP_PENALTY * dup + DISP_PENALTY * d2, self.G)
        too_far = np.zeros(self.G, dtype=bool)
        np.logical_or.at(too_far, self.g, d2 > MAX_DISP_M ** 2)
        c[too_far] = np.inf
        return c

    def disp2(self, th, du, dv):
        """Quadrat der Bewegung jeder Ecke (m²) durch Drehung und Verschiebung, vor dem Runden."""
        t = np.radians(th)[self.g]
        c, s = np.cos(t), np.sin(t)
        dx = (c - 1) * self.x - s * self.y + du[self.g] * self.sx[self.g]
        dy = s * self.x + (c - 1) * self.y + dv[self.g] * self.sy
        return dx * dx + dy * dy

    def search(self, full=False):
        G = self.G
        best = np.full(G, np.inf)
        bt, bu, bv = np.zeros(G), np.zeros(G), np.zeros(G)

        def try_(th, du, dv):
            nonlocal best
            c = self.cost(th, du, dv)
            better = c < best
            best = np.where(better, c, best)
            bt[better], bu[better], bv[better] = th[better], du[better], dv[better]

        rots, shifts = (FULL_ROT, FULL_SHIFT) if full else (COARSE_ROT, COARSE_SHIFT)
        one = np.ones(G)
        for th in rots:
            for du in shifts:
                for dv in shifts:
                    try_(th * one, du * one, dv * one)
        if not full:
            t0, u0, v0 = bt.copy(), bu.copy(), bv.copy()
            for dt in FINE_ROT:
                for ddu in FINE_SHIFT:
                    for ddv in FINE_SHIFT:
                        if dt == ddu == ddv == 0:
                            continue
                        try_(np.clip(t0 + dt, -MAX_ROT, MAX_ROT), u0 + ddu, v0 + ddv)
        return bt, bu, bv


def align_buildings(b, full_search: bool = False) -> dict:
    """Richtet alle Gebäude im Builder aus. Gibt eine Statistik zurück."""
    # Gebäude: geschlossene Wege mit building=*, Multipolygone mit building=* (alle Mitgliedsringe)
    member_of = {}
    for ri, (members, tags) in enumerate(b.relations):
        if _is_building(tags):
            for typ, ref, _role in members:
                if typ == "w":
                    member_of[ref - 1] = ri
    items_rings, ring_ways = [], []
    rel_item = {}
    for wi, (refs, tags) in enumerate(b.ways):
        if wi in member_of:
            ri = member_of[wi]
            if ri not in rel_item:
                rel_item[ri] = len(items_rings)
                items_rings.append([])
            items_rings[rel_item[ri]].append(len(ring_ways))
            ring_ways.append(wi)
        elif _is_building(tags) and len(refs) >= 4 and refs[0] == refs[-1]:
            items_rings.append([len(ring_ways)])
            ring_ways.append(wi)
    if not ring_ways:
        return {"gebaeude": 0}
    bset = set(ring_ways)
    buffered = _buffer_ways(b, ring_ways, {wi for wi in member_of})
    t_nodes = _insert_t_nodes(b, ring_ways)
    gid, ring_item = _groups(b, items_rings, ring_ways)
    R = _Rings(b, ring_ways, ring_item)
    P = _Problem(b, R, gid, int(gid.max()) + 1)
    th, du, dv = P.search(full=full_search)
    u, v = P.place(th, du, dv)
    disp = np.sqrt(P.disp2(th, du, dv))
    ang_new, ok_new = _angles(u * P.sx[P.g], v * P.sy, P.prev, P.next)
    u_orig = (P.x / P.sx[P.g] + P.cu[P.g])
    v_orig = (P.y / P.sy + P.cv[P.g])
    ang_r, ok_r = _angles(np.round(u_orig) * P.sx[P.g], np.round(v_orig) * P.sy, P.prev, P.next)

    # Knoten, die auch Netzlinien benutzen, bleiben stehen: Gebäude bekommt eigenen Knoten
    used_other = set()
    for wi, (refs, t) in enumerate(b.ways):
        if wi not in bset and any(k in t for k in FIXED_KEYS):
            used_other.update(refs)
    new_lon = np.round(u * UNIT * COORD_SCALE).astype(np.int64)
    new_lat = np.round(v * UNIT * COORD_SCALE).astype(np.int64)
    remap = {}
    moved = 0
    duplicated = 0
    # Ein Knoten gehört zu genau einer Gruppe (gemeinsamer Knoten = Berührung)
    for k, nid in enumerate(R.ref.tolist()):
        if nid in remap:
            continue
        if nid in used_other:
            remap[nid] = b._new_node(int(new_lon[k]), int(new_lat[k]), shared=False)
            duplicated += 1
        else:
            remap[nid] = nid
            b.node_lon[nid - 1] = int(new_lon[k])
            b.node_lat[nid - 1] = int(new_lat[k])
            b.node_shared[nid - 1] = False
            moved += 1
    # Wege umschreiben: neue Knoten, aufeinanderfolgende gleiche Lagen entfernen
    pos = 0
    for r, wi in enumerate(ring_ways):
        refs, tags = b.ways[wi]
        cl = len(refs) > 3 and refs[0] == refs[-1]
        n = len(refs) - 1 if cl else len(refs)
        out = []
        last = None
        for k in range(pos, pos + n):
            nn = remap[int(R.ref[k])]
            xy = (b.node_lon[nn - 1], b.node_lat[nn - 1])
            if xy != last:
                out.append(nn)
                last = xy
        if cl:
            while len(out) > 1 and (b.node_lon[out[-1] - 1], b.node_lat[out[-1] - 1]) == \
                    (b.node_lon[out[0] - 1], b.node_lat[out[0] - 1]):
                out.pop()
            out.append(out[0])
        if (cl and len(out) >= 4) or (not cl and len(out) >= 2):
            b.ways[wi] = (out, tags)
        pos += n
    e0 = np.abs(ang_r - P.ang0)[ok_r & P.ok0]
    e1 = np.abs(ang_new - P.ang0)[ok_new & P.ok0]

    def q(e, p):
        return round(float(np.percentile(e, p)), 1) if len(e) else None

    return {"gebaeude": len(items_rings), "gruppen": P.G, "ecken": len(R.ref),
            "winkel_median_vorher": q(e0, 50), "winkel_median_nachher": q(e1, 50),
            "winkel_p90_vorher": q(e0, 90), "winkel_p90_nachher": q(e1, 90),
            "knoten_verschoben": moved, "knoten_neu": duplicated, "gepuffert": buffered, "t_knoten": t_nodes,
            "bewegung_p95_m": round(float(np.percentile(disp, 95)), 2), "bewegung_max_m": round(float(disp.max()), 2)}
