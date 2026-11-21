"""Vorher/Nachher-Vergleich der Routing-Präferenz (docs/vektor/routing.md) auf der Basis-PBF.

Bildet die Kantenattribute des Styles nach (inc/access, Abschnitt 1 in lines, inc/routing_pref):
Zugang je Verkehrsmittel, road_class, road_speed, toll, unpaved. Darauf laufen Dijkstra-Routen
mit Kostenmodellen, die Garmins (nicht dokumentierte) Gewichtung annähern. Das ersetzt den Test
in BaseCamp/am Gerät nicht, zeigt aber, welche Wege die Attribute begünstigen, und weist nach,
dass sich keine für Autos befahrbare Kante ändert (Variante „basis“).

    python -I src/routing/compare_routes.py <basis.osm.pbf> [--json out.json]

Varianten: off (vor dem Prototyp, routing_pref=off), autofrei (nur A1–A4), mild (A1–A4 + Velorouten
auf Nebenstrassen Stufe 3; autofrei und mild nur hier modelliert), basis (A1–A5, Style-Standard),
stark (basis + A5b, velo_toll=stark), velo (A + B, routing_pref=velo, eigene Velo-Karte).
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
from collections import Counter, defaultdict

import osmium

CAR_EXCLUDE = {"path", "footway", "steps", "pedestrian", "cycleway", "bridleway", "via_ferrata"}
# Abschnitt 1 in src/style/swisstopo/lines: highway → (road_class, road_speed)
CLASS_SPEED = {
    "motorway": (4, 7), "motorway_link": (4, 4), "trunk": (4, 6), "trunk_link": (3, 4),
    "primary": (3, 5), "primary_link": (3, 3), "secondary": (2, 4), "secondary_link": (2, 3),
    "tertiary": (1, 3), "tertiary_link": (1, 3), "unclassified": (0, 3), "residential": (0, 2),
    "living_street": (0, 1), "service": (0, 1), "track": (0, 1), "pedestrian": (0, 1),
    "cycleway": (0, 1),
}
# Garmin-Tabelle (Style-Manual 4.6.5), Klasse 0 als Schrittgeschwindigkeit angenommen
SPEED_KMH = [5, 20, 40, 60, 80, 90, 110, 130]
UNPAVED = {"unpaved", "gravel", "fine_gravel", "compacted", "dirt", "ground", "grass", "earth", "mud", "sand"}
# Vermeidung = Kosten × AVOID_FACTOR. BaseCamp-Test 2026-11-04: wirkt fast wie ein Verbot.
AVOID_FACTOR = 1000
MAIN = {"trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"}
FOOTPATH = {"path", "footway", "steps", "via_ferrata", "bridleway"}

PLACES = {
    "St. Gallen Bf": (47.4233, 9.3698),
    "Wil Bf": (47.4625, 9.0427),
    "Wasserauen": (47.2849, 9.4285),
    "Säntis Gipfel": (47.2494, 9.3432),
    "Gossau SG": (47.4150, 9.2540),
    "Herisau": (47.3860, 9.2790),
    "Appenzell": (47.3310, 9.4090),
}


def edge_attrs(t, variant: str) -> dict | None:
    """Kantenattribute wie im Style. None = nicht routbar."""
    hw = t.get("highway")
    if hw is None or hw in ("proposed", "planned", "abandoned", "razed", "dismantled"):
        return None
    if hw not in CLASS_SPEED and hw not in FOOTPATH:
        return None
    rc, rs = CLASS_SPEED.get(hw, (0, 0))
    obj = t.get("swisstopo:objektart", "")
    # inc/access, vereinfacht
    access = t.get("access")
    if hw in ("path", "footway", "steps", "pedestrian", "cycleway", "bridleway", "via_ferrata") and access is None:
        access = "no"
    if access in ("agricultural", "forestry"):
        access = "no"
    mv = t.get("motor_vehicle") or t.get("vehicle") or access
    mc = t.get("motorcar") or mv
    narrow = obj in ("1m Weg", "1m Wegfragment", "Markierte Spur") or t.get("via_ferrata") == "yes"
    car = mc not in ("no", "private") and hw not in CAR_EXCLUDE and not narrow
    bike_tag = t.get("bicycle")
    if bike_tag is None:
        if hw in ("steps", "via_ferrata") or hw in ("motorway", "motorway_link", "trunk", "trunk_link") \
                or t.get("motorroad") == "yes" or t.get("via_ferrata") == "yes":
            bike_tag = "no"
        elif hw in ("path", "footway", "pedestrian", "cycleway", "track"):
            bike_tag = "yes"
        else:
            bike_tag = t.get("vehicle") or access or "yes"
    bike = bike_tag not in ("no", "private")
    foot_tag = t.get("foot")
    if foot_tag is None:
        foot_tag = "no" if hw in ("motorway", "motorway_link", "trunk", "trunk_link") or t.get("motorroad") == "yes" \
            else ("yes" if hw in FOOTPATH | {"pedestrian", "cycleway", "track"} else (access or "yes"))
    foot = foot_tag not in ("no", "private")
    unpaved = t.get("swisstopo:belagsart") == "Natur" or t.get("surface") in UNPAVED \
        or (t.get("tracktype") or "").startswith(("grade2", "grade3", "grade4", "grade5"))
    toll = False
    rb, rm, ww = t.get("route_bicycle"), t.get("route_mtb"), t.get("swisstopo:wanderweg")
    if variant != "off" and not car:
        rp = None
        if hw not in ("steps", "via_ferrata") and (rb in ("national", "regional") or rm in ("national", "regional")):
            rc, rs, rp = 1, 3, "velo"
        elif hw not in ("steps", "via_ferrata") and (rb or rm or hw == "cycleway"):
            rs, rp = 2, "velo"
        elif ww in ("Wanderweg", "Bergwanderweg") and hw in ("path", "footway", "bridleway", "pedestrian"):
            rs, rp = 1, "wander"
        if rp != "velo" and hw in FOOTPATH:
            toll = True
    if variant in ("velo", "mild"):
        if car and rb and hw in ("residential", "service", "unclassified", "track", "living_street"):
            rs = 3
    if variant == "stark" and not rb and not rm and hw in ("tertiary", "tertiary_link"):
        toll = True  # A5b (velo_toll=stark)
    if variant in ("basis", "stark", "velo") and not rb and not rm and hw in ("primary", "secondary", "primary_link", "secondary_link", "trunk", "trunk_link"):
        toll = True
    if variant == "velo":
        if car and rb and hw in ("tertiary", "tertiary_link"):
            rs = 4
        if not rb and not rm and hw in ("primary", "secondary", "primary_link", "secondary_link"):
            rs, toll = 2, True
    if variant != "off" and rb:
        unpaved = False  # A6: Veloland gilt als befahrbar (Flag entfernt, Signatur bleibt)
    oneway = t.get("oneway") in ("yes", "true", "1") or t.get("junction") == "roundabout"
    return dict(hw=hw, rc=rc, rs=rs, car=car, bike=bike, foot=foot, unpaved=unpaved, toll=toll,
                oneway=oneway, velo=bool(rb or rm), rb=rb or "", ww=ww or "", name=t.get("name", ""))


def _dist(la1, lo1, la2, lo2):
    return math.hypot((lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2)) * 111320, (la2 - la1) * 110540)


class Loader(osmium.SimpleHandler):
    def __init__(self, variants):
        super().__init__()
        self.variants = variants
        self.loc = {}
        self.edges = []          # (a, b, länge, {variante: attrs})
        self.changed = Counter()

    def way(self, w):
        t = {k.k: k.v for k in w.tags}
        if "highway" not in t:
            return
        at = {v: edge_attrs(t, v) for v in self.variants}
        if at["off"] is None:
            return
        for v in self.variants[1:]:
            a0, a1 = at["off"], at[v]
            if (a0["rc"], a0["rs"], a0["toll"]) != (a1["rc"], a1["rs"], a1["toll"]):
                self.changed[(v, "car" if a0["car"] else "nocar")] += 1
        nodes = [(n.ref, n.lat, n.lon) for n in w.nodes]
        for r, la, lo in nodes:
            self.loc[r] = (la, lo)
        for (a, la1, lo1), (b, la2, lo2) in zip(nodes, nodes[1:]):
            self.edges.append((a, b, _dist(la1, lo1, la2, lo2), at))


def cost_fn(profile: str, model: str, avoid: set):
    def f(e, L):
        if not e[profile]:
            return None
        if model == "distanz":
            c = L
        else:
            c = L / (SPEED_KMH[e["rs"]] / 3.6)
        if ("toll" in avoid and e["toll"]) or ("unpaved" in avoid and e["unpaved"]) \
                or ("major" in avoid and e["rc"] >= 3):  # Annahme: „Bundesstrassen“ = Klasse 3–4
            c *= AVOID_FACTOR
        return c
    return f


_ADJ = {}


def _graph(ld, variant, profile, model, avoid):
    key = (variant, profile, model, tuple(sorted(avoid)))
    if key not in _ADJ:
        cf = cost_fn(profile, model, avoid)
        adj = defaultdict(list)
        for a, b, L, at in ld.edges:
            e = at[variant]
            c = cf(e, L)
            if c is None:
                continue
            adj[a].append((b, c, L, e))
            if not (profile == "car" and e["oneway"]):
                adj[b].append((a, c, L, e))
        _ADJ.clear()  # Speicher: nur ein Graph gleichzeitig
        _ADJ[key] = adj
    return _ADJ[key]


def route(ld, variant, profile, model, avoid, src, dst):
    adj = _graph(ld, variant, profile, model, avoid)
    def near(p):
        return min(adj, key=lambda n: (ld.loc[n][0] - p[0]) ** 2 + ((ld.loc[n][1] - p[1]) * 0.68) ** 2)
    s, d = near(src), near(dst)
    dist, prev = {s: 0.0}, {}
    pq = [(0.0, s)]
    while pq:
        c, n = heapq.heappop(pq)
        if n == d:
            break
        if c > dist[n]:
            continue
        for m, w, L, e in adj[n]:
            nc = c + w
            if nc < dist.get(m, 1e18):
                dist[m] = nc
                prev[m] = (n, L, e)
                heapq.heappush(pq, (nc, m))
    if d not in prev:
        return None
    st = Counter()
    names = Counter()
    n = d
    while n != s:
        p, L, e = prev[n]
        st["km"] += L
        if e["velo"]:
            st["velo_route"] += L
        if e["ww"]:
            st["wanderweg"] += L
        if e["ww"] == "Bergwanderweg":
            st["bergwanderweg"] += L
        if e["hw"] in MAIN:
            st["hauptstrasse"] += L
        if e["unpaved"]:
            st["naturbelag"] += L
        if e["hw"] in FOOTPATH:
            st["pfad"] += L
        if e["toll"]:
            st["maut_flag"] += L
        if e["car"]:
            st["mit_autoverkehr"] += L
        names[e["name"] or f"({e['hw']})"] += L
        n = p
    out = {k: round(v / 1000, 2) for k, v in st.items()}
    out["wege"] = [f"{k} {v/1000:.1f}" for k, v in names.most_common(8)]
    return out


CASES = [
    ("Velo", "bike", "zeit", set(), "St. Gallen Bf", "Wil Bf"),
    ("Velo, Maut meiden", "bike", "zeit", {"toll"}, "St. Gallen Bf", "Wil Bf"),
    ("Velo, Maut+unbefestigt meiden", "bike", "zeit", {"toll", "unpaved"}, "St. Gallen Bf", "Wil Bf"),
    ("Velo, Maut+unbefestigt+Hauptstr. meiden", "bike", "zeit", {"toll", "unpaved", "major"}, "St. Gallen Bf", "Wil Bf"),
    ("Velo, Distanz, Maut+unbefestigt meiden", "bike", "distanz", {"toll", "unpaved"}, "St. Gallen Bf", "Wil Bf"),
    ("Velo, Distanz", "bike", "distanz", set(), "St. Gallen Bf", "Wil Bf"),
    ("Wandern", "foot", "zeit", set(), "Wasserauen", "Säntis Gipfel"),
    ("Wandern, Distanz", "foot", "distanz", set(), "Wasserauen", "Säntis Gipfel"),
    ("Fuss", "foot", "zeit", set(), "Gossau SG", "Herisau"),
    ("Auto", "car", "zeit", set(), "St. Gallen Bf", "Wil Bf"),
    ("Auto", "car", "zeit", set(), "Herisau", "Appenzell"),
    ("Auto, Maut meiden", "car", "zeit", {"toll"}, "St. Gallen Bf", "Wil Bf"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pbf")
    ap.add_argument("--json")
    a = ap.parse_args()
    variants = ["off", "autofrei", "mild", "basis", "stark", "velo"]
    ld = Loader(variants)
    ld.apply_file(a.pbf, locations=True)
    print("Geänderte Wege (road_class/road_speed/toll) gegenüber 'off':")
    for k, v in sorted(ld.changed.items()):
        print(f"  {k[0]:6s} {k[1]:6s} {v}")
    res = {"changed": {f"{k[0]}/{k[1]}": v for k, v in ld.changed.items()}, "routes": []}
    for label, prof, model, avoid, s, d in CASES:
        print(f"\n## {label}: {s} → {d}")
        for v in variants:
            r = route(ld, v, prof, model, avoid, PLACES[s], PLACES[d])
            res["routes"].append(dict(fall=label, von=s, nach=d, variante=v, **(r or {})))
            if r is None:
                print(f"  {v:6s} keine Route")
                continue
            keys = ["km", "velo_route", "wanderweg", "bergwanderweg", "hauptstrasse", "naturbelag", "pfad",
                    "mit_autoverkehr", "maut_flag"]
            print(f"  {v:6s} " + "  ".join(f"{k}={r.get(k, 0)}" for k in keys))
            print(f"         {'; '.join(r['wege'][:6])}")
    print("\n## Auto-Matrix (alle Ortspaare, Zeitmodell): Abweichung gegenüber 'off'")
    names = list(PLACES)
    res["auto_matrix"] = {}
    for v in variants[1:]:
        diff, tot, maxd = 0, 0, 0.0
        pairs = [(s, d) for s in names for d in names if s != d and "Säntis" not in s + d]
        r0s = [route(ld, "off", "car", "zeit", set(), PLACES[s], PLACES[d]) for s, d in pairs]
        r1s = [route(ld, v, "car", "zeit", set(), PLACES[s], PLACES[d]) for s, d in pairs]
        for r0, r1 in zip(r0s, r1s):
                tot += 1
                if r0 and r1 and abs(r0["km"] - r1["km"]) > 0.005:
                    diff += 1
                    maxd = max(maxd, abs(r1["km"] - r0["km"]))
        res["auto_matrix"][v] = dict(paare=tot, geaendert=diff, max_km_diff=round(maxd, 2))
        print(f"  {v:6s} {diff}/{tot} Routen geändert, max. {maxd:.2f} km Längenunterschied")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
