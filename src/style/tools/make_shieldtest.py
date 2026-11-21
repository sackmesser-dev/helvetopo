# -*- coding: utf-8 -*-
"""Shield-Testkarte (Gerätetest): je Variante ein Strassenstück Autobahn „A1“ und Hauptstrasse „7“.

Schreibt nach <ausgabeordner>: shieldtest.osm, style/ (lines, points), shieldtest_typ.txt.
Gebaut wird mit src/style/build_shieldtest.sh. Ort: synthetische Linien westlich von Wil
(Testgebiet), Zeilen von Nord nach Süd, links Autobahn, rechts Hauptstrasse, Beschriftung der
Variante als Label-Punkt (0x2800) am Westende jeder Linie.

Varianten:
  S1–S6  Garmin-Shields interstate, shield, round, hbox, box, oval (Typen 0x01 / 0x03)
  N1     Nummer als normales Label ohne Shield (Typen 0x01 / 0x03, Schrift schwarz)
  L1/L2  Nummer als Label, TYP-Schriftfarbe rot bzw. blau (eigene Linientypen, Strassenoptik)
  L3/L4  wie L1/L2, aber LargeFont
  B1/B2  Nummer als weisses Label auf einem breiten roten bzw. blauen Band (eigener Linientyp)
"""
import os
import sys

OUT = sys.argv[1]
ROT = '#D8232A'    # Schweizer Autobahnschild (Annäherung)
BLAU = '#1F5FAD'   # Schweizer Hauptstrassenschild (Annäherung)

SHIELDS = ['interstate', 'shield', 'round', 'hbox', 'box', 'oval']
# Zeile: (Kürzel, Beschreibung, Autobahn-Regel, Hauptstrassen-Regel)
ROWS = []
for i, s in enumerate(SHIELDS, 1):
    ROWS.append(('S%d' % i, 'Shield %s' % s,
                 "{ name '${ref|highway-symbol:%s}' } [0x01 resolution 18]" % s,
                 "{ name '${ref|highway-symbol:%s}' } [0x03 resolution 18]" % s))
ROWS += [
    ('N1', 'Label ohne Shield', "{ name '${ref}' } [0x01 resolution 18]", "{ name '${ref}' } [0x03 resolution 18]"),
    ('L1', 'Label farbig Normal', "{ name '${ref}' } [0x11410 resolution 18]", "{ name '${ref}' } [0x11411 resolution 18]"),
    ('L3', 'Label farbig Large', "{ name '${ref}' } [0x11414 resolution 18]", "{ name '${ref}' } [0x11415 resolution 18]"),
    ('B1', 'Band mit weisser Nummer', "{ name '${ref}' } [0x11412 resolution 18]", "{ name '${ref}' } [0x11413 resolution 18]"),
]

LON0, LAT0, DLAT = 9.000, 47.470, -0.004   # Zeilen ~450 m auseinander
AB = (LON0 + 0.004, LON0 + 0.034)          # ~2,3 km
HS = (LON0 + 0.042, LON0 + 0.072)

os.makedirs(os.path.join(OUT, 'style'), exist_ok=True)
nodes, ways = [], []
nid = [0]


def node(lon, lat, tags=None):
    nid[0] += 1
    nodes.append((nid[0], lon, lat, tags or {}))
    return nid[0]


lines_rules, wid = [], 0
for r, (code, desc, ab_rule, hs_rule) in enumerate(ROWS):
    lat = LAT0 + r * DLAT
    for side, (x0, x1), ref, rule in (('ab', AB, 'A1', ab_rule), ('hs', HS, '7', hs_rule)):
        nd = [node(x0 + (x1 - x0) * k / 4, lat) for k in range(5)]
        wid += 1
        ways.append((wid, nd, {'test:variant': code, 'test:side': side, 'ref': ref}))
        lines_rules.append("test:variant=%s & test:side=%s %s" % (code, side, rule))
        label = '%s %s %s' % (code, 'AB' if side == 'ab' else 'HS', desc)
        node(x0 - 0.0005, lat + 0.0006, {'test:label': label})

with open(os.path.join(OUT, 'shieldtest.osm'), 'w', encoding='utf-8') as f:
    f.write("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6' generator='make_shieldtest'>\n")
    f.write("<bounds minlat='%.4f' minlon='%.4f' maxlat='%.4f' maxlon='%.4f'/>\n"
            % (LAT0 + len(ROWS) * DLAT - 0.002, LON0 - 0.01, LAT0 + 0.003, HS[1] + 0.005))
    for i, lon, lat, tags in nodes:
        if tags:
            f.write("<node id='%d' version='1' lat='%.7f' lon='%.7f'>\n" % (i, lat, lon))
            for k, v in tags.items():
                f.write("  <tag k='%s' v='%s'/>\n" % (k, v))
            f.write("</node>\n")
        else:
            f.write("<node id='%d' version='1' lat='%.7f' lon='%.7f'/>\n" % (i, lat, lon))
    for i, nd, tags in ways:
        f.write("<way id='%d' version='1'>\n" % i)
        for n in nd:
            f.write("  <nd ref='%d'/>\n" % n)
        for k, v in tags.items():
            f.write("  <tag k='%s' v='%s'/>\n" % (k, v))
        f.write("</way>\n")
    f.write("</osm>\n")

with open(os.path.join(OUT, 'style', 'lines'), 'w', encoding='utf-8') as f:
    f.write('# Shield-Testkarte, erzeugt von src/style/tools/make_shieldtest.py\n')
    f.write('\n'.join(lines_rules) + '\n')
with open(os.path.join(OUT, 'style', 'points'), 'w', encoding='utf-8') as f:
    f.write("test:label=* { name '${test:label}' } [0x2800 resolution 18]\n")
for fn, txt in (('version', '1\n'), ('polygons', '# keine Flächen\n'), ('relations', '# keine Relationen\n')):
    with open(os.path.join(OUT, 'style', fn), 'w', encoding='utf-8') as f:
        f.write(txt)
with open(os.path.join(OUT, 'style', 'options'), 'w', encoding='utf-8') as f:
    f.write('levels = 0:24, 1:22, 2:20, 3:18\n')


def line(t, name, fill, width, border, font, fontcol):
    out = ['[_line]', 'Type=0x%x' % t, 'String=0x02,%s' % name, 'String=0x04,%s' % name,
           'FontStyle=%s' % font, 'DayCustomColor=%s' % fontcol, 'NightCustomColor=%s' % fontcol,
           'LineWidth=%d' % width]
    if border:
        out += ['BorderWidth=2', 'Xpm="0 0 2 0"', '"a c %s"' % fill, '"b c #000000"']
    else:
        out += ['BorderWidth=0', 'Xpm="0 0 1 0"', '"a c %s"' % fill]
    return '\n'.join(out + ['[end]', ''])


extra = [
    line(0x11410, 'Test L1 Autobahn rot', '#FBBF39', 5, True, 'NormalFont', ROT),
    line(0x11411, 'Test L2 Hauptstrasse blau', '#F5AE95', 6, True, 'NormalFont', BLAU),
    line(0x11414, 'Test L3 Autobahn rot gross', '#FBBF39', 5, True, 'LargeFont', ROT),
    line(0x11415, 'Test L4 Hauptstrasse blau gross', '#F5AE95', 6, True, 'LargeFont', BLAU),
    line(0x11412, 'Test B1 Band rot', ROT, 14, False, 'NormalFont', '#FFFFFF'),
    line(0x11413, 'Test B2 Band blau', BLAU, 14, False, 'NormalFont', '#FFFFFF'),
]
base = open(sys.argv[2], encoding='utf-8').read()
with open(os.path.join(OUT, 'shieldtest_typ.txt'), 'w', encoding='utf-8') as f:
    f.write(base.rstrip('\n') + '\n\n' + '\n'.join(extra))
print('%d Zeilen, %d Linien' % (len(ROWS), len(ways)))
