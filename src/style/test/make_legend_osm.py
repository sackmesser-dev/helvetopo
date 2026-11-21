#!/usr/bin/env python3
"""Erzeugt die Legenden-Testkarte src/style/test/legende.osm.

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python3 -I src/style/test/make_legend_osm.py > src/style/test/legende.osm

Inhalt: je eine Probe jeder Objektart des Styles (Linien als Zeilen, Flächen als Quadrate,
Punkte als Raster), jeweils mit Beschriftung, plus ein kleines zusammenhängendes Strassen-
und Wegnetz für Routing-Tests (Auto/Velo/Fuss). Lage: im Testgebiet bei Herisau/Waldstatt,
die Geometrie ist frei erfunden und hat mit der echten Topografie nichts zu tun.
"""
from xml.sax.saxutils import quoteattr

LON0, LAT0 = 9.2600, 47.3900       # linke obere Ecke der Legende
DLON_100M = 100 / 75500.0          # ~100 m in Länge bei 47.4° N
DLAT_100M = 100 / 111200.0

nodes = []   # (id, lat, lon, tags)
ways = []    # (id, [nodeids], tags)
rels = []    # (id, [(type, ref, role)], tags)
_nid = [0]
_wid = [0]


def node(lat, lon, tags=None):
    _nid[0] -= 1
    nodes.append((_nid[0], lat, lon, tags or {}))
    return _nid[0]


def way(nids, tags):
    _wid[0] -= 1
    ways.append((_wid[0], nids, tags))
    return _wid[0]


def xy(x, y):
    """x, y in 100-m-Schritten ab der Ecke (y nach Süden)."""
    return LAT0 - y * DLAT_100M, LON0 + x * DLON_100M


def label(x, y, text):
    lat, lon = xy(x, y)
    node(lat, lon, {'place': 'locality', 'name': text})


def line(x0, y, length, tags, text=None, closed=False):
    pts = [node(*xy(x0 + i * length / 4.0, y)) for i in range(5)]
    way(pts, tags)
    if text:
        label(x0 + length + 0.3, y, text)


def square(x, y, size, tags, text=None):
    pts = [node(*xy(x, y)), node(*xy(x + size, y)), node(*xy(x + size, y + size)),
           node(*xy(x, y + size))]
    way(pts + [pts[0]], tags)
    if text:
        label(x + size + 0.2, y + size / 2.0, text)


# ------------------------------------------------------------------ Spalte 1: Linien
LINES = [
    ({'highway': 'motorway', 'ref': 'A1', 'swisstopo:objektart': 'Autobahn', 'swisstopo:verkehrsbedeutung': 'Hochleistungsstrasse'}, 'Autobahn A1'),
    ({'highway': 'trunk', 'ref': '7', 'motorroad': 'yes', 'swisstopo:objektart': 'Autostrasse'}, 'Autostrasse'),
    ({'highway': 'motorway_link', 'swisstopo:objektart': 'Ausfahrt', 'oneway': 'yes'}, 'Ein-/Ausfahrt'),
    ({'highway': 'primary', 'ref': '8', 'name': 'Durchgangsstrasse', 'swisstopo:objektart': '8m Strasse', 'swisstopo:verkehrsbedeutung': 'Durchgangsstrasse'}, 'Durchgangsstrasse'),
    ({'highway': 'secondary', 'name': 'Verbindungsstrasse', 'swisstopo:objektart': '6m Strasse', 'swisstopo:verkehrsbedeutung': 'Verbindungsstrasse'}, 'Verbindungsstrasse'),
    ({'highway': 'tertiary', 'swisstopo:objektart': '6m Strasse', 'name': 'Strasse 6m'}, '6m Strasse'),
    ({'highway': 'unclassified', 'swisstopo:objektart': '4m Strasse', 'name': 'Strasse 4m'}, '4m Strasse'),
    ({'highway': 'service', 'swisstopo:objektart': '3m Strasse', 'swisstopo:belagsart': 'Hart'}, '3m Strasse Hartbelag'),
    ({'highway': 'track', 'swisstopo:objektart': '3m Strasse', 'swisstopo:belagsart': 'Natur'}, '3m Strasse Naturbelag'),
    ({'highway': 'track', 'swisstopo:objektart': '2m Weg', 'swisstopo:belagsart': 'Hart'}, '2m Weg Hartbelag'),
    ({'highway': 'track', 'swisstopo:objektart': '2m Weg', 'swisstopo:belagsart': 'Natur'}, '2m Weg Naturbelag'),
    ({'highway': 'path', 'swisstopo:objektart': '1m Weg'}, '1m Weg'),
    ({'highway': 'path', 'swisstopo:objektart': 'Markierte Spur'}, 'Markierte Spur'),
    ({'highway': 'steps'}, 'Treppe'),
    ({'highway': 'path', 'swisstopo:objektart': '1m Weg', 'via_ferrata': 'yes', 'swisstopo:verkehrsbeschraenkung': 'Gesicherte Kletterpartie'}, 'Klettersteig'),
    ({'highway': 'secondary', 'tunnel': 'yes', 'name': 'Tunnel'}, 'Strassentunnel'),
    ({'route': 'ferry', 'motor_vehicle': 'yes'}, 'Autofaehre'),
    ({'route': 'ferry'}, 'Personenfaehre'),
    ({'railway': 'rail', 'tracks': '2'}, 'Normalspur mehrspurig'),
    ({'railway': 'rail'}, 'Normalspur'),
    ({'railway': 'narrow_gauge'}, 'Schmalspur'),
    ({'railway': 'rail', 'service': 'siding'}, 'Anschlussgleis'),
    ({'railway': 'tram'}, 'Tram'),
    ({'railway': 'rail', 'tunnel': 'yes'}, 'Bahntunnel'),
    ({'aerialway': 'cable_car', 'name': 'Luftseilbahn'}, 'Luftseilbahn'),
    ({'aerialway': 'drag_lift', 'name': 'Skilift'}, 'Skilift'),
    ({'aerialway': 'goods'}, 'Transportseilbahn'),
    ({'waterway': 'river', 'name': 'Sitter'}, 'Fluss'),
    ({'waterway': 'stream', 'name': 'Urnaesch-Bach'}, 'Bach'),
    ({'waterway': 'stream', 'intermittent': 'yes'}, 'Trockenrinne'),
    ({'waterway': 'stream', 'tunnel': 'culvert'}, 'Eingedolter Bach'),
    ({'waterway': 'waterfall', 'name': 'Wasserfall'}, 'Wasserfall (Linie)'),
    ({'man_made': 'pipeline', 'substance': 'water'}, 'Druckleitung'),
    ({'contour': 'elevation', 'ele': '900', 'contour_ext': 'elevation_minor'}, 'Hoehenkurve 900'),
    ({'contour': 'elevation', 'ele': '950', 'contour_ext': 'elevation_medium'}, 'Zwischenkurve'),
    ({'contour': 'elevation', 'ele': '1000', 'contour_ext': 'elevation_major'}, 'Zaehlkurve 1000'),
    ({'contour': 'elevation', 'ele': '2100', 'swisstopo:untergrund': 'fels'}, 'Hoehenkurve Fels'),
    ({'contour': 'elevation', 'ele': '2400', 'swisstopo:untergrund': 'gletscher', 'contour_ext': 'elevation_major'}, 'Zaehlkurve Gletscher'),
    ({'boundary': 'administrative', 'admin_level': '2'}, 'Landesgrenze'),
    ({'boundary': 'administrative', 'admin_level': '4'}, 'Kantonsgrenze'),
    ({'boundary': 'administrative', 'admin_level': '6'}, 'Bezirksgrenze'),
    ({'boundary': 'administrative', 'admin_level': '8'}, 'Gemeindegrenze'),
    ({'boundary': 'national_park'}, 'Nationalpark'),
    ({'power': 'line'}, 'Hochspannungsleitung'),
    ({'barrier': 'wall'}, 'Mauer'),
    ({'man_made': 'embankment'}, 'Gewaesserverbauung'),
    ({'man_made': 'dyke'}, 'Damm/Boeschung'),
    ({'natural': 'cliff'}, 'Felswand'),
    ({'natural': 'ridge', 'name': 'Grat'}, 'Grat'),
    ({'waterway': 'dam'}, 'Staumauer'),
    ({'aeroway': 'runway', 'ref': '09/27'}, 'Piste'),
]
for i, (tags, text) in enumerate(LINES):
    line(0, 1 + i * 0.6, 4, tags, text)

# ------------------------------------------------------------------ Spalte 2: Flächen
POLYS = [
    ({'natural': 'water', 'water': 'lake', 'name': 'Testsee'}, 'See'),
    ({'natural': 'water', 'water': 'river'}, 'Fluss Flaeche'),
    ({'natural': 'water', 'intermittent': 'yes'}, 'See wechselnd'),
    ({'leisure': 'swimming_pool'}, 'Schwimmbecken'),
    ({'natural': 'wood', 'name': 'Testwald'}, 'Wald'),
    ({'natural': 'wood', 'wood': 'open'}, 'Wald offen'),
    ({'natural': 'scrub'}, 'Gebueschwald'),
    ({'natural': 'glacier', 'name': 'Testgletscher'}, 'Gletscher'),
    ({'natural': 'bare_rock'}, 'Fels'),
    ({'natural': 'scree'}, 'Geroell'),
    ({'natural': 'wetland'}, 'Feuchtgebiet'),
    ({'landuse': 'vineyard'}, 'Reben'),
    ({'landuse': 'orchard'}, 'Obstanlage'),
    ({'landuse': 'plant_nursery'}, 'Baumschule'),
    ({'landuse': 'cemetery'}, 'Friedhof'),
    ({'leisure': 'golf_course'}, 'Golfplatz'),
    ({'tourism': 'camp_site', 'name': 'Camping'}, 'Campingplatz'),
    ({'leisure': 'park'}, 'Park'),
    ({'leisure': 'pitch'}, 'Sportplatz'),
    ({'landuse': 'landfill'}, 'Deponie'),
    ({'power': 'substation'}, 'Unterwerk'),
    ({'amenity': 'hospital', 'name': 'Spital'}, 'Spitalareal'),
    ({'amenity': 'parking'}, 'Parkplatz'),
    ({'aeroway': 'runway', 'area': 'yes'}, 'Hartbelagpiste'),
    ({'aeroway': 'runway', 'area': 'yes', 'surface': 'grass'}, 'Graspiste'),
    ({'man_made': 'solar_panel'}, 'Solaranlage'),
    ({'building': 'greenhouse'}, 'Treibhaus'),
    ({'building': 'yes'}, 'Gebaeude'),
    ({'barrier': 'wall', 'area': 'yes'}, 'Mauer gross'),
    ({'building': 'roof'}, 'Flugdach'),
    ({'waterway': 'dam', 'area': 'yes'}, 'Staudamm (Flaeche)'),
    ({'man_made': 'bridge'}, 'Bruecke'),
    ({'landuse': 'residential', 'name': 'Siedlung'}, 'Siedlung'),
]
for i, (tags, text) in enumerate(POLYS):
    square(9 + (i % 2) * 4, 1 + (i // 2) * 2, 1.5, tags, text)

# ------------------------------------------------------------------ Spalte 3: Punkte
POINTS = [
    ({'place': 'city', 'name': 'St. Gallen'}, None),
    ({'place': 'town', 'name': 'Herisau'}, None),
    ({'place': 'village', 'name': 'Waldstatt'}, None),
    ({'place': 'hamlet', 'name': 'Schachen'}, None),
    ({'place': 'isolated_dwelling', 'name': 'Hof Egg'}, None),
    ({'place': 'suburb', 'name': 'Quartier'}, None),
    ({'natural': 'ridge', 'name': 'Grat'}, None),
    ({'natural': 'hill', 'name': 'Huegel', 'ele': '981'}, None),
    ({'historic': 'boundary_stone'}, 'Grenzstein'),
    ({'highway': 'motorway_junction', 'ref': '79', 'name': 'Gossau'}, None),
    ({'building': 'yes', 'name': 'Gebaeudename'}, None),
    ({'man_made': 'tower', 'tower:type': 'bell_tower', 'name': 'Sakraler Turm'}, None),
    ({'natural': 'valley', 'name': 'Neckertal'}, None),
    ({'natural': 'peak', 'name': 'Saentis', 'ele': '2502', 'swisstopo:objektart': 'Hauptgipfel'}, None),
    ({'natural': 'peak', 'name': 'Gipfel', 'ele': '1834'}, None),
    ({'natural': 'saddle', 'name': 'Pass', 'ele': '1520'}, None),
    ({'swisstopo:objektart': 'Hoehenkote', 'ele': '812'}, None),
    ({'natural': 'cave_entrance', 'name': 'Hoehle'}, None),
    ({'natural': 'stone'}, 'Felsblock'),
    ({'natural': 'spring', 'name': 'Quelle'}, None),
    ({'waterway': 'waterfall', 'name': 'Wasserfall'}, None),
    ({'amenity': 'fountain', 'name': 'Brunnen'}, None),
    ({'man_made': 'cross', 'summit:cross': 'yes'}, 'Gipfelkreuz'),
    ({'amenity': 'place_of_worship', 'building': 'chapel', 'name': 'Kapelle'}, None),
    ({'amenity': 'place_of_worship', 'name': 'Kirche'}, None),
    ({'historic': 'wayside_shrine'}, 'Bildstock'),
    ({'historic': 'memorial', 'name': 'Denkmal'}, None),
    ({'historic': 'ruins', 'name': 'Ruine'}, None),
    ({'man_made': 'tower', 'tower:type': 'observation', 'name': 'Aussichtsturm'}, None),
    ({'man_made': 'mast'}, 'Antenne'),
    ({'man_made': 'water_tower'}, 'Wasserturm'),
    ({'man_made': 'chimney'}, 'Hochkamin'),
    ({'man_made': 'tower', 'name': 'Turm'}, None),
    ({'power': 'generator', 'generator:source': 'wind'}, 'Windturbine'),
    ({'man_made': 'survey_point', 'ele': '1003'}, 'Triangulation'),
    ({'tourism': 'viewpoint', 'name': 'Aussicht'}, None),
    ({'tourism': 'alpine_hut', 'name': 'Berghuette', 'ele': '1780'}, None),
    ({'tourism': 'hotel', 'name': 'Hotel'}, None),
    ({'tourism': 'camp_site', 'name': 'Camping'}, None),
    ({'amenity': 'restaurant', 'name': 'Gasthaus'}, None),
    ({'railway': 'station', 'name': 'Bahnhof'}, None),
    ({'aerialway': 'station', 'name': 'Seilbahnstation'}, None),
    ({'highway': 'bus_stop', 'name': 'Bushalt'}, None),
    ({'amenity': 'ferry_terminal', 'name': 'Schiffstation'}, None),
    ({'aeroway': 'aerodrome', 'name': 'Flugplatz'}, None),
    ({'aeroway': 'helipad', 'name': 'Heliport'}, None),
    ({'amenity': 'parking'}, 'Parkplatz'),
    ({'barrier': 'lift_gate'}, 'Durchfahrtssperre'),
    ({'amenity': 'hospital', 'name': 'Spital'}, None),
]
for i, (tags, text) in enumerate(POINTS):
    x, y = 19 + (i % 3) * 3, 1 + (i // 3) * 1.2
    lat, lon = xy(x, y)
    node(lat, lon, tags)
    if text:
        label(x + 0.3, y, text)

# ------------------------------------------------------------------ Routing-Netz (unten)
# 6x4-Gitter aus Kreuzungen, gemischte Typen; Knoten werden geteilt, damit Routing möglich ist.
GX, GY, ROWS, COLS = 0, 32, 4, 6
grid = [[node(*xy(GX + c * 2, GY + r * 2)) for c in range(COLS)] for r in range(ROWS)]
row_tags = [
    {'highway': 'primary', 'name': 'Hauptstrasse', 'ref': '8', 'swisstopo:objektart': '6m Strasse', 'swisstopo:verkehrsbedeutung': 'Durchgangsstrasse'},
    {'highway': 'residential', 'name': 'Dorfstrasse', 'swisstopo:objektart': '4m Strasse'},
    {'highway': 'track', 'name': 'Feldweg', 'swisstopo:objektart': '3m Strasse', 'swisstopo:belagsart': 'Natur'},
    {'highway': 'path', 'name': 'Wanderweg', 'swisstopo:objektart': '1m Weg'},
]
for r in range(ROWS):
    way(grid[r], row_tags[r])
col_tags = [
    {'highway': 'secondary', 'name': 'Talstrasse', 'swisstopo:objektart': '6m Strasse', 'swisstopo:verkehrsbedeutung': 'Verbindungsstrasse'},
    {'highway': 'unclassified', 'name': 'Bergstrasse', 'swisstopo:objektart': '4m Strasse'},
    {'highway': 'service', 'name': 'Zufahrt Hof', 'swisstopo:objektart': '3m Strasse', 'access': 'private'},
    {'highway': 'track', 'name': 'Alpweg', 'swisstopo:objektart': '2m Weg', 'swisstopo:belagsart': 'Natur', 'motor_vehicle': 'no'},
    {'highway': 'path', 'name': 'Bergweg', 'swisstopo:objektart': '1m Weg'},
    {'highway': 'cycleway', 'name': 'Veloweg', 'swisstopo:objektart': '2m Weg', 'swisstopo:belagsart': 'Hart'},
]
for c in range(COLS):
    way([grid[r][c] for r in range(ROWS)], col_tags[c])
# Einbahn und Kreisel
way([grid[1][0], node(*xy(GX + 1, GY + 3)), grid[2][1]], {'highway': 'residential', 'name': 'Einbahn', 'oneway': 'yes'})
# Adressen für die Suche
for k, (r, c) in enumerate(((1, 1), (1, 2), (1, 3))):
    lat, lon = xy(GX + c * 2 + 0.3, GY + r * 2 + 0.2)
    node(lat, lon, {'addr:street': 'Dorfstrasse', 'addr:housenumber': str(k + 1),
                    'addr:city': 'Waldstatt', 'addr:postcode': '9104'})

# ------------------------------------------------------------------ Ausgabe
print("<?xml version='1.0' encoding='UTF-8'?>")
print("<osm version='0.6' generator='Helvetopo make_legend_osm.py'>")
print("  <bounds minlat='%.6f' minlon='%.6f' maxlat='%.6f' maxlon='%.6f'/>" % (
    xy(0, 42)[0], LON0 - 0.001, LAT0 + 0.001, xy(30, 0)[1]))
for nid, lat, lon, tags in nodes:
    if tags:
        print("  <node id='%d' version='1' lat='%.7f' lon='%.7f'>" % (nid, lat, lon))
        for k, v in tags.items():
            print("    <tag k=%s v=%s/>" % (quoteattr(k), quoteattr(v)))
        print("  </node>")
    else:
        print("  <node id='%d' version='1' lat='%.7f' lon='%.7f'/>" % (nid, lat, lon))
for wid, nids, tags in ways:
    print("  <way id='%d' version='1'>" % wid)
    for n in nids:
        print("    <nd ref='%d'/>" % n)
    for k, v in tags.items():
        print("    <tag k=%s v=%s/>" % (quoteattr(k), quoteattr(v)))
    print("  </way>")
print("</osm>")
