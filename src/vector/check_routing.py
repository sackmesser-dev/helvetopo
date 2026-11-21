"""Plausibilitätsprüfung des Routing-Graphen direkt auf der PBF (ohne mkgmap).

Prüft für Auto (mit Einbahn, ohne motor_vehicle=no) und zu Fuss, ob Testorte gegenseitig
erreichbar sind, und gibt die Grösse der Zusammenhangskomponenten aus.

    .venv/bin/python -m src.vector.check_routing work/vector/testgebiet.osm.pbf
"""

from __future__ import annotations

import heapq
import math
import sys
from collections import defaultdict

import osmium

# Wie der Style (inc/access): path/footway/steps/pedestrian/cycleway/bridleway sind für Autos
# gesperrt, track nur bei motor_vehicle=no.
CAR_EXCLUDE = {"path", "footway", "steps", "pedestrian", "cycleway", "bridleway"}
SAENTIS = (47.2494, 9.3432)
PLACES = {
    "Wil SG": (47.4615, 9.0455),
    "St. Gallen": (47.4245, 9.3767),
    "Appenzell": (47.3310, 9.4090),
    "Herisau": (47.3860, 9.2790),
    "Schwägalp": (47.2560, 9.3190),
    "Gossau SG": (47.4150, 9.2540),
    "Säntis Gipfel": (47.2494, 9.3432),
}


class Graph(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.loc = {}
        self.car = defaultdict(list)
        self.foot = defaultdict(list)
        self.bike = defaultdict(list)

    def way(self, w):
        hw = w.tags.get("highway")
        if not hw and w.tags.get("route") != "ferry":
            return
        refs = [(n.ref, n.lat, n.lon) for n in w.nodes]
        for r, la, lo in refs:
            self.loc[r] = (la, lo)
        t = w.tags
        car = (hw not in CAR_EXCLUDE and t.get("motor_vehicle") not in ("no", "private")
               and t.get("motorcar") not in ("no", "private")
               and t.get("access") not in ("no", "private") and hw is not None)
        bike = (t.get("bicycle") not in ("no", "private") and t.get("access") not in ("no", "private")
                and hw not in ("steps",) and t.get("highway") not in ("motorway", "motorway_link")
                and (hw is not None or t.get("route") == "ferry"))
        foot = t.get("foot") != "no" and t.get("access") != "no"
        oneway = t.get("oneway") == "yes" or t.get("junction") == "roundabout"
        for (a, la1, lo1), (b, la2, lo2) in zip(refs, refs[1:]):
            d = _dist(la1, lo1, la2, lo2)
            if car:
                self.car[a].append((b, d))
                if not oneway:
                    self.car[b].append((a, d))
            if foot:
                self.foot[a].append((b, d))
                self.foot[b].append((a, d))
            if bike:
                self.bike[a].append((b, d))
                if not oneway:
                    self.bike[b].append((a, d))


def _dist(la1, lo1, la2, lo2):
    x = (lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2)) * 111320
    y = (la2 - la1) * 110540
    return math.hypot(x, y)


def nearest(g, adj, la, lo):
    return min((n for n in adj), key=lambda n: (g.loc[n][0] - la) ** 2 + ((g.loc[n][1] - lo) * 0.68) ** 2)


def dijkstra(adj, src, dst):
    dist = {src: 0.0}
    pq = [(0.0, src)]
    while pq:
        d, n = heapq.heappop(pq)
        if n == dst:
            return d
        if d > dist.get(n, 1e18):
            continue
        for m, w in adj.get(n, ()):
            nd = d + w
            if nd < dist.get(m, 1e18):
                dist[m] = nd
                heapq.heappush(pq, (nd, m))
    return None


def main(path):
    g = Graph()
    g.apply_file(path, locations=True)
    ok = True
    for mode, adj in (("Auto", g.car), ("Fuss", g.foot)):
        nodes = {k: nearest(g, adj, *v) for k, v in PLACES.items()}
        for a in PLACES:
            for b in PLACES:
                if a >= b:
                    continue
                d1 = dijkstra(adj, nodes[a], nodes[b])
                d2 = dijkstra(adj, nodes[b], nodes[a])
                f = lambda d: "—" if d is None else f"{d / 1000:.1f} km"
                print(f"{mode:5} {a:11} → {b:11}: {f(d1):>9}   zurück: {f(d2):>9}")
                ok &= d1 is not None and d2 is not None
    # Kein Auto-/Velo-Weg bis zum Säntisgipfel: Der Gipfel (nächster Fussweg-Knoten) darf von der
    # Schwägalp aus nur zu Fuss erreichbar sein. (Garmin weicht auf gesperrte Wege aus, wenn es
    # keine erlaubte Verbindung gibt; das ist Geräteverhalten, kein Datenfehler.)
    summit = nearest(g, g.foot, *SAENTIS)
    for mode, adj in (("Auto", g.car), ("Velo", g.bike)):
        start = nearest(g, adj, *PLACES["Schwägalp"])
        d = dijkstra(adj, start, summit) if summit in adj else None
        good = d is None
        ok &= good
        print(f"{mode:5} Schwägalp → Säntisgipfel: "
              f"{'keine Route (ok)' if good else f'{d / 1000:.1f} km (FEHLER)'}")
    print("OK" if ok else "FEHLER: Prüfung nicht bestanden")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "work/vector/testgebiet.osm.pbf"))
