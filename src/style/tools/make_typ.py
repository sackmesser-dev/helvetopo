#!/usr/bin/env python3
"""Erzeugt die TYP-Quelle src/style/typ/swisstopo.txt (mkgmap-TYP-Textformat).

Aufruf (aus dem Repo-Wurzelverzeichnis):
    python3 -I src/style/tools/make_typ.py > src/style/typ/swisstopo.txt
    python3 -I src/style/tools/make_typ.py --soll-ist > docs/stil/soll-ist.md
    Option --px-per-mm N: andere Umrechnung (Standard 6,25 = GPSMAP 66/67; Montana 7xx ≈ 7,4)

Farben: SMV25-QGIS-Darstellungsmodell von swisstopo (OGD-Hilfsdatei), siehe docs/stil/stil.md.
Symbole: eigene Pixelgrafiken im Stil der Landeskarte, keine Kopie der DKM-Symbolschrift.
Nachtfarben werden aus den Tagfarben abgeleitet (night()).

Grenzen (mkgmap typ-compiler.txt, GPSMAP/Montana):
  - Flächenmuster genau 32x32, 2 Farben (Tag) + 2 Farben (Nacht), Hintergrund darf "none" sein.
  - Linienmuster Breite 32, Höhe = Linienbreite (hier max. 13 für die Landesgrenze), 2 Farben (+2 Nacht).
  - Linien ohne Muster: LineWidth + BorderWidth, je 2 Farben Tag/Nacht.
  - POI-Symbole: bis 255 Farben; hier max. 15x15 px, damit sie auf 240x400-Displays nicht dominieren.
"""

import sys

# ---------------------------------------------------------------- Farben (SMV25)
C = {
    'weiss': 'FFFFFF', 'schwarz': '000000', 'dunkel': '262626', 'fels': '3E3E3E',
    'autobahn': 'FBBF39', 'durchgang': 'F5AE95', 'verbindung': 'FFF582',
    'bahn': 'DD1919', 'gewaesser': '0088D0', 'see': 'D2EEFF', 'fluss': '9CD5F8',
    'wald': 'CDE6BE',  # SMV25-QGIS (LK-Pixelkarte gemessen: C8E0B0, inkl. Schummerung)
    'gruen': '70B446', 'areal': 'E7F3E1', 'grenzband': 'ECA8C8',
    'grenzlinie': 'C22976', 'braun': 'D7963C', 'grau': 'CCCCCC', 'deponie': 'F0DABC',
    'solar': 'FFFF9B', 'nationalpark': 'A0CF83', 'spital': 'F2F2F2', 'seil': '333333',
    'siedlung': 'BEBEBE', 'gletscher_bg': 'F3F9FE', 'gletscher_fg': '8CC4EC',
    'fels_bg': 'F0F0F0', 'fels_fg': '8A8A8A', 'geroell_fg': '6E6E6E',
    'fels_raster': '3F3F3F', 'gletscher_raster': '006BC7',
}

NIGHT_BG = (24, 26, 32)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def night(h, f=0.42):
    """Nachtfarbe: dunkle Farben werden hell (Kontrast auf dunklem Grund), helle gedämpft.
    f = Anteil der Tagfarbe (Rest: Nachthintergrund)."""
    if h == 'none':
        return 'none'
    r, g, b = rgb(h)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum < 70:  # Schwarz/Dunkelgrau -> helles Grau
        v = 200 - int(lum)
        return '%02X%02X%02X' % (v, v, v)
    r, g, b = (int(c * f + nb * (1 - f)) for c, nb in zip((r, g, b), NIGHT_BG))
    return '%02X%02X%02X' % (r, g, b)


def night_area(h):
    """Flächen nachts stärker abdunkeln als Linien, damit Strassen und Gewässer lesbar bleiben."""
    if h != 'none' and sum(rgb(h)) < 3 * 70:
        return '8C8C8C'  # Gebäude
    return night(h, 0.24)


def night_font(h):
    """Schriftfarben nachts aufhellen."""
    if h == '000000':
        return 'E6E6E6'
    r, g, b = rgb(h)
    return '%02X%02X%02X' % tuple(int(c * 0.6 + 255 * 0.4) for c in (r, g, b))


def col(name_or_hex):
    return C.get(name_or_hex, name_or_hex)


def xc(h):
    return 'none' if h == 'none' else '#' + h


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from typ_i18n import fr_it  # noqa: E402

out = []
w = out.append


def strings(names, font=None, day_font=None):
    de, en = names
    fr, it = fr_it(de)
    # DE zuerst: Geräte und BaseCamp nehmen den ersten String, wenn die Sprache fehlt.
    w('String=0x02,%s' % de)
    w('String=0x01,%s' % fr)
    w('String=0x05,%s' % it)
    w('String=0x04,%s' % en)
    if font:
        w('FontStyle=%s' % font)
    if day_font:
        w('DayCustomColor=#%s' % day_font)
        w('NightCustomColor=#%s' % night_font(day_font))


# ---------------------------------------------------------------- Linien
# Neutrale Namen der Routingtypen: BaseCamp und Geräte nennen unbenannte Abschnitte in der
# Wegbeschreibung mit dem TYP-Namen („Biegen Sie links ab auf …“). Die Objektklassen stehen in
# der Soll-Ist-Liste; hier nur Wörter, die sich in Abbiegehinweisen lesen lassen.
# BaseCamp setzt im Deutschen fest „auf die …“, deshalb nur feminine Namen (Test 8).
NEUTRAL = {
    0x01: ('Autobahn', 'Motorway'), 0x02: ('Autostrasse', 'Expressway'), 0x09: ('Ausfahrt', 'Ramp'),
    0x03: ('Hauptstrasse', 'Main road'), 0x04: ('Strasse', 'Road'), 0x05: ('Strasse', 'Road'),
    0x06: ('Nebenstrasse', 'Minor road'), 0x07: ('Nebenstrasse', 'Minor road'), 0x08: ('Gasse', 'Lane'),
    0x0a: ('Naturstrasse', 'Track'), 0x0e: ('Feldstrasse', 'Track'), 0x10: ('Wegstrecke', 'Path'),
    0x16: ('Pfadstrecke', 'Path'), 0x0f: ('Wegspur', 'Trace'), 0x11: ('Treppe', 'Steps'),
    0x12: ('Kletterroute', 'Via ferrata'), 0x13: ('Tunnelstrecke', 'Tunnel'),
    0x1a: ('Autofähre', 'Car ferry'), 0x1b: ('Fähre', 'Ferry'),
}


def neutral(t, names):
    """Neutraler Name für Routing-, Übersichts- (0x10a..) und LK50-Typen (0x10b..)."""
    if t in NEUTRAL:
        return NEUTRAL[t]
    if (t & 0xfff00) in (0x10900, 0x10a00, 0x10b00) and (t & 0xff) in NEUTRAL:
        return NEUTRAL[t & 0xff]
    return names


def line_solid(t, names, fill, width, border=None, bwidth=0, font=None, fontcol=None):
    names = neutral(t, names)
    fill = col(fill)
    w('[_line]')
    w('Type=0x%x' % t)
    strings(names, font or 'NoLabel', fontcol)
    w('LineWidth=%d' % width)
    if border:
        border = col(border)
        w('BorderWidth=%d' % bwidth)
        w('Xpm="0 0 4 0"')
        w('"a c %s"' % xc(fill))
        w('"b c %s"' % xc(border))
        w('"c c %s"' % xc(night(fill)))
        w('"d c %s"' % xc(night(border)))
    else:
        w('Xpm="0 0 2 0"')
        w('"a c %s"' % xc(fill))
        w('"c c %s"' % xc(night(fill)))
    w('[end]')
    w('')


def line_bitmap(t, names, fg, bg, rows, font=None, fontcol=None):
    """rows: Liste von Strings (Länge 32 nach Wiederholung), 'x' = Vordergrund, '.' = Hintergrund."""
    names = neutral(t, names)
    if t in NEUTRAL and t < 0x20 and font == 'SmallFont':
        font = 'NormalFont'
    fg, bg = col(fg), col(bg)
    rows = [(r * 32)[:32] for r in rows]
    w('[_line]')
    w('Type=0x%x' % t)
    strings(names, font or 'NoLabel', fontcol)
    w('UseOrientation=Y')
    w('Xpm="32 %d 4 1"' % len(rows))
    w('"x c %s"' % xc(fg))
    w('". c %s"' % xc(bg))
    w('"X c %s"' % xc(night(fg)))
    w('"o c %s"' % xc(night(bg)))
    for r in rows:
        w('"%s"' % r)
    w('[end]')
    w('')


def tick(period, pos, n=1):
    s = ['.'] * period
    for i in range(n):
        s[(pos + i) % period] = 'x'
    return ''.join(s)


# ---------------------------------------------------------------- Umrechnung mm -> px
# Regel (docs/stil/stil.md, "Umrechnung"), Etappe 4:
#   Linien und Muster: LK-Strich in Geländebreite bei Garmin-Auflösung 24 (1 Karteneinheit = 2,39 m
#   = 1 px). 1 mm bei 1:25 000 = 25 m = 10,46 px  ->  K = 10,4 px/mm (per --px-per-mm änderbar).
#   Symbole: physische LK-Grösse auf dem GPSMAP 66/67 (0,163 mm/px)  ->  K_SYM = 6,25 px/mm.
K = 10.4
if '--px-per-mm' in sys.argv:
    K = float(sys.argv[sys.argv.index('--px-per-mm') + 1])
K_SYM = 6.25
# Gerät für Strichbreiten: GPSMAP 66/67, 158 dpi = 0,160 mm/px → 6,25 px/mm (wie style-qa ab
# Bericht 00:46 und wie K_SYM). LK-Strich in Originalgrösse bei 1:25 000 (Auflösung 23).
K_DEV = 6.25
# Strassen in Auflösung 24: volle LK-Geländebreite bei der Gerätezoomstufe, in der Auflösung 24
# gezeichnet wird (≈ 1:12 500) → LK25 doppelt so gross → 2 × K_DEV = 12,5 px/mm.
K_24 = 2 * K_DEV


def px(mm, minimum=1):
    """mm bei 1:25 000 -> ganze Gerätepixel (kaufmännisch gerundet, mindestens `minimum`)."""
    return max(minimum, int(mm * K + 0.5))


def dash(on_mm, off_mm, *more):
    """Strichmuster (mm, abwechselnd Strich/Lücke) -> 32-px-Zeile. Die Periode wird so gestreckt,
    dass eine ganze Zahl von Wiederholungen in 32 px passt (Garmin-Muster sind 32 px lang)."""
    seq = (on_mm, off_mm) + more
    period = sum(seq) * K
    n = max(1, int(32 / period + 0.5))
    scale = 32.0 / (n * period)
    row = []
    for i in range(32):
        pos = ((i + 0.5) / scale) % period
        acc, on = 0.0, True
        for j, seg in enumerate(seq):
            acc += seg * K
            if pos < acc:
                on = (j % 2 == 0)
                break
        row.append('x' if on else '.')
    return ''.join(row)


SOLL = []  # (Art, Typ, Name, Soll aus SMV25-QGIS, Ist in der TYP, Bemerkung)


def soll(kind, t, name, sollw, istw, note=''):
    SOLL.append((kind, t, name, sollw, istw, note))


def road(t, names, fill, inner_mm, border_mm, smv, font='SmallFont', note='', min_inner=1):
    """Strasse mit schwarzem Rand (SMV: zwei SimpleLines, Rand = (gesamt - innen) / 2)."""
    if (t < 0x100 or 0x10a00 <= t <= 0x10a08) and font == 'SmallFont':
        font = 'NormalFont'  # Strassennamen in 24 (Test 7) und 23 (Review 1: zu klein)
    # Über die Gesamtbreite runden (die misst man im Bild): gesamt = round((innen + 2 × Rand) × K),
    # Rand = round(Rand × K), Füllung = gesamt − 2 × Rand (mind. 1 px).
    border = px(border_mm)
    total = px(inner_mm + 2 * border_mm)
    inner = max(min_inner, total - 2 * border)
    line_solid(t, names, fill, inner, 'schwarz', border, font)
    if _SOLL_ON:
        soll('Linie', t, names[0], ('%s: #%s innen %.2f mm, Rand #000000 %.2f mm' % (smv, col(fill), inner_mm, border_mm)).replace('.', ','),
             '%d + 2×%d px' % (inner, border), note)


_SOLL_ON = True
OVERVIEW = 0x10a00   # Übersichtstypen der Strassen: 0x10a00 | Routingtyp, nicht routingfähig


def streets(k, off):
    """Alle Strassen- und Wegsignaturen mit Umrechnung k. off = 0: Routingtypen (Auflösung 24),
    off = OVERVIEW: gleiche Signaturen als Übersichtstypen (Auflösung <= 23)."""
    global K, _SOLL_ON
    k_save, K = K, k
    _SOLL_ON = (off == 0)
    ov = ' (Übersicht)' if off else ''

    def T(t):
        return off | t

    def S(*a):
        if off == 0:
            soll(*a)

    # SMV-Rand ist überall 0,12 mm je Seite (gesamt − innen), z. B. 6 m: 0,70 − 0,46 = 0,24.
    road(T(0x01), ('Autobahn' + ov, 'Motorway'), 'autobahn', 0.36, 0.16, 'Autobahn (round) 0,68/0,36', 'NormalFont',
         'SMV zeichnet je Fahrbahn eine Linie. TLM liefert ebenfalls getrennte Fahrbahnen.')
    road(T(0x02), ('Autostrasse' + ov, 'Expressway'), 'autobahn', 0.46, 0.12, 'Autostrasse/Zufahrt (6m, round) 0,70/0,46', 'NormalFont')
    road(T(0x09), ('Ein-/Ausfahrt' + ov, 'Ramp'), 'autobahn', 0.38, 0.12, 'Autostrasse Einfahrt/Raststaette (4m) 0,62/0,38')
    road(T(0x03), ('Durchgangsstrasse' + ov, 'Main road'), 'durchgang', 0.54, 0.12, 'Durchgangsstrasse (8m, round) 0,78/0,54', 'NormalFont',
         'eine Breite für alle Breitenklassen (Routingtyp je Farbe), häufigste Klasse 8 m. SMV 3m–10m: 0,30–0,62 mm innen.')
    road(T(0x04), ('Verbindungsstrasse' + ov, 'Connecting road'), 'verbindung', 0.46, 0.12, 'Verbindungsstrasse (6m, round) 0,70/0,46', 'NormalFont',
         'wie Durchgangsstrasse')
    road(T(0x05), ('Strasse 6 m und breiter' + ov, 'Road 6 m+'), 'weiss', 0.46, 0.12, 'Strasse (6m, round) 0,70/0,46',
         note='10 m (0,62) und 8 m (0,54) zusammengefasst, Typ-Mangel')
    road(T(0x06), ('Strasse 4 m' + ov, 'Road 4 m'), 'weiss', 0.38, 0.12, 'Strasse (4m, round) 0,62/0,38')
    road(T(0x07), ('Strasse 3 m' + ov, 'Road 3 m'), 'weiss', 0.30, 0.12, 'Strasse (3m, round) 0,54/0,30')
    road(T(0x08), ('Strasse 2 m, Hartbelag' + ov, 'Lane 2 m, paved'), 'weiss', 0.22, 0.12, 'Strasse (2m, round) 0,46/0,22')
    # Naturbelag: weiss 0,54 mm, Ränder als Punktreihe (FontMarker 0,265 mm)
    _dots = dash(0.265, 0.265)
    _nb = [_dots] * px(0.12) + ['.'] * max(1, px(0.54) - 2 * px(0.12)) + [_dots] * px(0.12)
    line_bitmap(T(0x0a), ('Fahrweg, Naturbelag' + ov, 'Unpaved road'), 'schwarz', 'weiss', _nb, 'SmallFont')
    S('Linie', 0x0a, 'Fahrweg, Naturbelag', 'Strasse (3m, Naturbelag): #FFFFFF 0,54 mm, Randpunkte #000000 0,265 mm',
      '%d px, Randzeilen %s' % (len(_nb), _dots[:8]), 'Punkte als Strichmuster der Randzeilen')
    line_solid(T(0x0e), ('Weg 2 m' + ov, 'Track 2 m'), 'schwarz', px(0.18), font='SmallFont')
    S('Linie', 0x0e, 'Weg 2 m', 'Weg (2m, Naturbelag): #000000 0,18 mm', '%d px' % px(0.18))
    _w2n = dash(2.99861, 0.299861)
    line_bitmap(T(0x10), ('Weg 2 m, nicht befahrbar' + ov, 'Track 2 m, no vehicles'), 'schwarz', 'none',
                [_w2n] * px(0.18), 'SmallFont')
    S('Linie', 0x10, 'Weg 2 m, nicht befahrbar', 'Weg (2m, nicht befahrbar): #000000 0,18 mm, Strich 3,00/0,30 mm',
      '%d px, %s' % (px(0.18), _w2n))
    _weg1 = dash(1.19945, 0.299861)
    line_bitmap(T(0x16), ('Weg 1 m' + ov, 'Path 1 m'), 'schwarz', 'none', [_weg1] * px(0.18), 'SmallFont')
    S('Linie', 0x16, 'Weg 1 m', 'Weg (1m): #000000 0,18 mm, Strich 1,20/0,30 mm', '%d px, %s' % (px(0.18), _weg1))
    _spur = dash(0.265, 0.6)
    line_bitmap(T(0x0f), ('Wegspur' + ov, 'Trace'), 'schwarz', 'none', [_spur] * px(0.265), 'SmallFont')
    S('Linie', 0x0f, 'Wegspur', 'Markierte Spur: Punkte #000000 0,265 mm', '%d px, %s' % (px(0.265), _spur),
      'Abstand der Punkte geschätzt (MarkerLine-Intervall nicht ausgelesen)')
    line_bitmap(T(0x11), ('Treppe' + ov, 'Steps'), 'schwarz', 'none', ['x.', 'x.', 'x.', 'x.'])
    S('Linie', 0x11, 'Treppe', 'Strasse (Treppe): Querstriche #000000', '4 px Querstriche')
    line_bitmap(T(0x12), ('Klettersteig' + ov, 'Via ferrata'), 'schwarz', 'none',
                [tick(8, 3), 'x', tick(8, 3)], 'SmallFont')
    S('Linie', 0x12, 'Klettersteig', '– (SMV ohne eigene Signatur)', '3 px, Linie mit Querstrichen', 'eigene Signatur')
    _tun = dash(0.790223, 0.493889)
    _tw = max(3, px(0.54))
    line_bitmap(T(0x13), ('Strassentunnel' + ov, 'Road tunnel'), 'schwarz', 'none',
                [_tun] + ['.'] * (_tw - 2) + [_tun], 'SmallFont')
    S('Linie', 0x13, 'Strassentunnel', 'Strasse (Tunnel): gestrichelte Ränder #000000, Strich 0,79/0,49 mm',
      '%d px, Ränder %s' % (_tw, _tun), 'ein Tunneltyp für alle Klassen (Routingtypen knapp)')
    K = k_save
    _SOLL_ON = True


W = ('weiss',)
# ---------------------------------------------------------------- Strassen (T45_DKM25_STRASSE)
# Auflösung 24: Routingtypen, volle LK-Geländebreite (K_24 = 14,2 px/mm, Test 9).
streets(K_24, 0)
# Auflösung <= 23: Übersichtstypen in LK-Strichbreite am Gerät (180 dpi, K_DEV = 7,09 px/mm).
streets(K_DEV, OVERVIEW)
soll('Linie', OVERVIEW, 'Strassen-Übersichtstypen 0x10a01–0x10a16',
     'wie die Routingtypen, mm × %.2f px/mm (Gerät 180 dpi)' % K_DEV,
     'Auflösung ≤ 23, nicht routingfähig, nur Routennummer als Label',
     'TYP hat nur eine Breite je Typ. Darum hat jede Zoomstufe einen eigenen Typ (Routing läuft auf Auflösung 24).')

# Grobstufen LK100/LK200 (Auflösung 12–20, Etappe 26): Autobahn, Autostrasse, Durchgangs- und
# Verbindungsstrasse mit eigenen Typen 0x10900|Typ, Signatur wie die Übersichtstypen. Eigene Typen,
# damit Durchgangs- und Verbindungsstrassen hier ohne Routennummer bleiben (Test 19: die Nummern
# verdrängten in Auflösung 20 den Ortsnamen St. Gallen); 0x10a.. gilt nur noch in 21–23.
GROB = 0x10900
_k_save = K
K = K_DEV
_SOLL_ON = False
road(GROB | 0x01, ('Autobahn (Grobstufe)', 'Motorway'), 'autobahn', 0.36, 0.16, '', 'NormalFont')
road(GROB | 0x02, ('Autostrasse (Grobstufe)', 'Expressway'), 'autobahn', 0.46, 0.12, '', 'NormalFont')
road(GROB | 0x03, ('Durchgangsstrasse (Grobstufe)', 'Main road'), 'durchgang', 0.54, 0.12, '')
road(GROB | 0x04, ('Verbindungsstrasse (Grobstufe)', 'Connecting road'), 'verbindung', 0.46, 0.12, '')
# Etappe 27: Autobahn/Autostrasse in 12–16 ohne Nummer (Test 20: Schilder verdrängten „St. Gallen“ bei 5 km)
road(GROB | 0x05, ('Autobahn (Übersicht)', 'Motorway'), 'autobahn', 0.36, 0.16, '', 'NormalFont')
road(GROB | 0x06, ('Autostrasse (Übersicht)', 'Expressway'), 'autobahn', 0.46, 0.12, '', 'NormalFont')
_SOLL_ON = True
K = _k_save
soll('Linie', GROB, 'Strassen-Grobstufe 0x10901–0x10904', 'LK100/LK200: Autobahn, Autostrasse, Durchgangs- und Verbindungsstrasse',
     'wie Übersichtstypen, Auflösung 12–20 (Autobahn), 14–20, 16–20, 18–20', 'nur Autobahn/Autostrasse mit Nummer, Tunnel durchgezogen')

# LK50-Stufe (Auflösung 21–22, Test 8): Nebenstrassen und Wege zurückhaltend, damit sich
# Haupt- und Verbindungsstrassen (Übersichtstypen mit Rand) abheben. Eigene Typen 0x10b00|Typ.
LK50 = 0x10b00
_k_save = K
K = K_DEV
# Review 2 (Übersicht 3–5 km zu leer, Mass SMR200): Strassen ≥ 6 m schon in 19–20 als feine Doppellinie.
line_solid(GROB | 0x07, ('Nebenstrasse (Übersicht)', 'Minor road (overview)'), 'weiss', 1, 'schwarz', 1, 'NoLabel')
soll('Linie', GROB | 0x07, 'Strasse 6 m, Übersicht', 'LK200: Nebenstrasse weiss mit schwarzem Rand', '1 + 2×1 px', 'Auflösung 19–20 (Review 2)')
line_solid(LK50 | 0x06, ('Strasse 4 m (LK50)', 'Road 4 m (LK50)'), 'weiss', 1, 'schwarz', 1, 'SmallFont')
soll('Linie', LK50 | 0x06, 'Strasse 4 m, Stufe LK50', 'LK50: Nebenstrasse als feine Doppellinie', '1 + 2×1 px', 'Auflösung 21–22, generalisiert')
line_solid(LK50 | 0x07, ('Strasse 3 m (LK50)', 'Road 3 m (LK50)'), 'schwarz', 1)
line_solid(LK50 | 0x08, ('Strasse 2 m (LK50)', 'Lane 2 m (LK50)'), 'schwarz', 1)
soll('Linie', LK50 | 0x07, 'Strasse 3 m / 2 m, Stufe LK50', 'LK50: schmale Strassen als feine Linie', '1 px #000000', 'Auflösung 22, generalisiert (Linie statt Doppellinie)')
_lk50w = dash(1.2, 0.6)
for _t, _n in ((0x0a, 'Fahrweg'), (0x0e, 'Weg 2 m'), (0x10, 'Weg 2 m nicht befahrbar'), (0x16, 'Weg 1 m')):
    line_bitmap(LK50 | _t, (_n + ' (LK50)', 'Track (LK50)'), 'schwarz', 'none', [_lk50w])
soll('Linie', LK50 | 0x16, 'Fahrwege und Wege, Stufe LK50', 'LK50: Wege schwarz gestrichelt', '1 px #000000, %s' % _lk50w, 'Auflösung 22, generalisiert')
K = _k_save

_faehre = dash(0.987778, 0.395111)
line_bitmap(0x1a, ('Autofähre', 'Car ferry'), 'schwarz', 'none', [_faehre], 'SmallFont')
soll('Linie', 0x1a, 'Autofähre', 'Autofähre: #000000 0,14 mm, Strich 0,99/0,40 mm', '1 px, %s' % _faehre)
_pf = dash(2.48708, 0.994834)
line_bitmap(0x1b, ('Personenfähre', 'Ferry'), 'schwarz', 'none', [_pf], 'SmallFont')
soll('Linie', 0x1b, 'Personenfähre', 'Personenfähre (ohne Seil): #000000 0,12 mm, Strich 2,49/0,99 mm', '1 px, %s' % _pf)
line_solid(0x27, ('Piste', 'Runway'), 'weiss', 3, 'dunkel', 1)
soll('Linie', 0x27, 'Piste (Linie)', 'Hartbelagpiste ist Fläche (T60), Rand #262626 0,12 mm', '3 + 2×1 px', 'Rückfall für Pisten ohne Fläche')

# Alle übrigen Linien (Bahn, Gewässer, Kurven, Grenzen, Bauten): LK-Strichbreite am Gerät (K_DEV),
# eine Breite für alle Zoomstufen. Nur Strassen in Auflösung 24 nutzen die Geländebreite K.
K_LINE = K
K = K_DEV
# ---------------------------------------------------------------- Grenzen (T53, T54)
def band(total_mm, line_mm=0.16):
    """Grenzband: Linie #C22976 mittig auf Band #ECA8C8 (ungerade Zeilenzahl, Linie in der Mitte)."""
    n = px(total_mm)
    if n % 2 == 0:
        n += 1
    lw = px(line_mm)
    rows = ['.'] * n
    for i in range((n - lw) // 2, (n - lw) // 2 + lw):
        rows[i] = 'x'
    return rows


blau = C['gewaesser']
BAHN = 0.7     # Review 1: Bahnlinien dünner
GRENZE = 0.8   # Review 1: Landes-/Kantonsgrenze etwas dünner

# Nicht-Strassen-Linien je Zoomstufe (Etappe 13): Bahn, Gewässer, Grenzen, Leitungen.
# Auflösung ≤ 23: bisherige Typen mit K_DEV (LK-Strich am Gerät). Auflösung 24: eigene Typen mit
# K_24 (LK-Geländebreite), Typcodes nach D24.
D24 = {
    0x14: 0x10c14, 0x1f: 0x10c1f, 0x18: 0x10c18, 0x26: 0x10c06, 0x1e: 0x10c1e, 0x1c: 0x10c1c, 0x29: 0x10c09,
    0x10e00: 0x10d00, 0x10e01: 0x10d01, 0x10e02: 0x10d02, 0x10e03: 0x10d03, 0x10e04: 0x10d04,
    0x10e05: 0x10d05, 0x10e07: 0x10d07, 0x10e08: 0x10d08, 0x10e10: 0x10d10, 0x10e11: 0x10d11,
    0x10e12: 0x10d12, 0x10f04: 0x11104, 0x10f05: 0x11105, 0x10f06: 0x11106, 0x10f0e: 0x1110e,
}


def others(k, res24):
    global K
    k_save, K = K, k

    def T(t):
        return D24[t] if res24 else t

    def S(*a):
        if not res24:
            soll(*a)

    # ---------------------------------------------------------------- Bahn, Seilbahn (T44, T42)
    # Review 1 (Benutzer): Bahn wirkte zu auffällig → Breiten × BAHN, am Gerät mind. 2 px Normalspur.
    _ns = max(2, px(0.32 * BAHN))
    line_solid(T(0x14), ('Normalspur', 'Railway'), 'bahn', _ns)
    S('Linie', 0x14, 'Normalspur', 'Normalspur (Einspur): #DD1919 0,32 mm', '%d px' % _ns, 'Breite × 0,7 (Review 1)')
    _ms_w = px(0.22 * BAHN)
    _ms_r = max(1, (px(0.76 * BAHN) - _ms_w + 1) // 2)
    line_bitmap(T(0x10e00), ('Normalspur, mehrspurig', 'Railway, multi-track'), 'bahn', 'weiss',
                ['x'] * _ms_r + ['.'] * _ms_w + ['x'] * _ms_r)
    S('Linie', 0x10e00, 'Normalspur mehrspurig', 'Normalspur (Mehrspur): #DD1919 0,76 mm, Mitte #FFFFFF 0,22 mm',
         '%d px (%d rot, %d weiss, %d rot)' % (2 * _ms_r + _ms_w, _ms_r, _ms_w, _ms_r), 'Breite × 0,7 (Review 1)')
    line_solid(T(0x10e01), ('Schmalspur, Standseilbahn', 'Narrow gauge, funicular'), 'bahn', px(0.22 * BAHN))
    S('Linie', 0x10e01, 'Schmalspur', 'Schmalspur (Einspur): #DD1919 0,22 mm', '%d px' % px(0.22 * BAHN), 'Breite × 0,7 (Review 1)')
    line_solid(T(0x10e02), ('Anschlussgleis', 'Siding'), 'bahn', px(0.10))
    S('Linie', 0x10e02, 'Anschlussgleis', 'Anschlussgleis: #DD1919 0,10 mm', '%d px' % px(0.10), 'gleich breit wie Schmalspur (Mindestbreite 1 px)')
    line_solid(T(0x10e03), ('Tram', 'Tram'), 'bahn', px(0.10))
    S('Linie', 0x10e03, 'Tram, Gleise auf Strasse', 'Gleise auf Strasse: #DD1919 0,10 mm', '%d px' % px(0.10))
    _bt = dash(0.8, 0.5)
    line_bitmap(T(0x10e07), ('Bahntunnel', 'Railway tunnel'), 'bahn', 'none', [_bt, _bt])
    S('Linie', 0x10e07, 'Bahntunnel', 'Eisenbahn Tunnel: #DD1919 gestrichelt', '2 px, %s' % _bt, 'Strichlänge geschätzt')
    line_bitmap(T(0x10e04), ('Luftseilbahn, Gondelbahn, Sesselbahn', 'Aerial cableway'), 'bahn', 'none',
                [tick(16, 8), 'x', tick(16, 8)], 'SmallFont', C['bahn'])
    S('Linie', 0x10e04, 'Luftseilbahn', 'Luftseilbahn: #DD1919 0,20 mm + Stützensymbole', '1 px + Querstriche alle 16 px')
    line_bitmap(T(0x10e05), ('Skilift', 'Ski lift'), 'braun', 'none',
                [tick(12, 6), 'x', tick(12, 6)], 'SmallFont', C['braun'])
    S('Linie', 0x10e05, 'Skilift', 'Skilift: #D7963C 0,15 mm + Symbole', '1 px + Querstriche')
    line_bitmap(T(0x10e08), ('Transportseilbahn', 'Goods cableway'), 'seil', 'none',
                [tick(10, 5), 'x', tick(10, 5)])
    S('Linie', 0x10e08, 'Transportseil, Förderband', 'Transportseil: #000000 0,18 mm, Symbole #333333', '1 px + Querstriche')

    # ---------------------------------------------------------------- Gewässer (T57)
    blau = C['gewaesser']
    line_solid(T(0x1f), ('Fluss', 'River'), 'gewaesser', px(0.30), font='NormalFont', fontcol=blau)
    S('Linie', 0x1f, 'Fluss', 'Fliessgewässer (0,12–0,40): #0088D0', '%d px (0,30 mm)' % px(0.30),
         'SMV-Breite je Gewässer variabel, hier zwei Stufen')
    line_solid(T(0x18), ('Bach', 'Stream'), 'gewaesser', px(0.14), font='SmallFont', fontcol=blau)
    S('Linie', 0x18, 'Bach', 'Fliessgewässer (0,14): #0088D0', '%d px' % px(0.14))
    if not res24:
        # Review 2: Bäche der Gewässerklasse 4 in der Übersicht (19–21), ohne Namen.
        line_solid(0x10e1b, ('Bach (Übersicht)', 'Stream (overview)'), 'gewaesser', 1)
    if res24:
        # Review 1: Quellbäche (Flussordnung 1–2) in 24 dünner als die übrigen Bäche.
        line_solid(0x10c17, ('Bach klein', 'Small stream'), 'gewaesser', px(0.10), font='SmallFont', fontcol=blau)
    _tr = dash(0.265, 0.35)
    line_bitmap(T(0x26), ('Trockenrinne', 'Dry stream bed'), 'schwarz', 'none', [_tr], 'SmallFont')
    S('Linie', 0x26, 'Trockenrinne', 'Trockenrinne: Punkte #000000 0,265 mm', '1 px, %s' % _tr)
    line_solid(T(0x10e10), ('Druckleitung', 'Water pipeline'), 'gewaesser', px(0.22))
    S('Linie', 0x10e10, 'Druckleitung', 'Druckleitung: #0088D0 0,22 mm + Symbol', '%d px' % px(0.22), 'ohne Symbole')
    line_bitmap(T(0x10e12), ('Eingedolter Bach', 'Culvert'), 'gewaesser', 'none', ['xx..'])
    line_bitmap(T(0x10e11), ('Wasserfall', 'Waterfall'), 'gewaesser', 'none',
                ['..x...x.', '.x.x.x.x', 'x...x...'], 'SmallFont', blau)
    S('Linie', 0x10e11, 'Wasserfall', 'Wasserfall: #0088D0 + Symbol #F2F2F2/#0088D0', '3 px Zickzack', 'eigenes Muster')

    # Review 1: Grenzbänder etwas dünner (× GRENZE), Linie bleibt 1 px.
    _lg = band(2.0 * GRENZE)
    line_bitmap(T(0x1e), ('Landesgrenze', 'National border'), 'grenzlinie', 'grenzband', _lg)
    S('Linie', 0x1e, 'Landesgrenze', 'Landesgrenze: Band #ECA8C8 2,0 mm, Linie #C22976 0,16 mm', '%d px Band, 1 px Linie' % len(_lg),
         'auf ungerade Zeilenzahl aufgerundet (Linie mittig)')
    _kg = band(1.0 * GRENZE)
    line_bitmap(T(0x1c), ('Kantonsgrenze', 'Canton border'), 'grenzlinie', 'grenzband', _kg)
    S('Linie', 0x1c, 'Kantonsgrenze', 'Kantonsgrenze: Band #ECA8C8 1,0 mm, Linie #C22976 0,16 mm', '%d px Band, 1 px Linie' % len(_kg))
    line_solid(T(0x10f04), ('Bezirksgrenze', 'District border'), 'grenzband', px(0.4))
    S('Linie', 0x10f04, 'Bezirksgrenze', 'Bezirksgrenze: #ECA8C8 0,40 mm', '%d px' % px(0.4))
    _gg = dash(2.99861, 0.599723)
    line_bitmap(T(0x10f05), ('Gemeindegrenze', 'Municipal border'), 'grenzband', 'none', [_gg] * px(0.4))
    S('Linie', 0x10f05, 'Gemeindegrenze', 'Gemeindegrenze: #ECA8C8 0,40 mm, Strich 3,0/0,6 mm', '%d px, %s' % (px(0.4), _gg))
    line_solid(T(0x10f06), ('Nationalpark', 'National park'), 'nationalpark', 2)
    S('Linie', 0x10f06, 'Nationalpark', 'Nationalpark: #A0CF83 0,16 mm + Band', '2 px', 'ohne Band')

    _hs = dash(2.46945, 0.395111, 0.197556, 0.395111)
    line_bitmap(T(0x29), ('Hochspannungsleitung', 'Power line'), 'gewaesser', 'none', [_hs])
    S('Linie', 0x29, 'Hochspannungsleitung', 'Hochspannungsleitung: #0088D0 0,14 mm, Strich-Punkt 2,47/0,40/0,20/0,40 mm', '1 px, %s' % _hs)
    line_solid(T(0x10f0e), ('Gewässerverbauung, Hafensteg', 'Embankment, pier'), 'gewaesser', px(0.14))
    S('Linie', 0x10f0e, 'Gewässerverbauung, Hafensteg', 'Gewässerverbauung/Hafensteg: #0088D0 0,14/0,18 mm', '%d px' % px(0.14))

    K = k_save


others(K_DEV, False)
others(K_24, True)
# Fluss für Auflösung 21 (Signatur wie 0x1f). Namen in 21 nur für Gewässerklasse 4 (Goldach, Steinach),
# kleinere Flüsse erst ab 22 als 0x1f. Test 20: die Steinach durch das Zentrum von St. Gallen.
_k_save = K
K = K_DEV
line_solid(0x10e1a, ('Fluss', 'River'), 'gewaesser', px(0.30), font='NormalFont', fontcol=blau)
K = _k_save
soll('Linie', 0x10c00, 'Bahn, Gewässer, Grenzen in Auflösung 24 (0x10c.., 0x10d.., 0x111..)',
     'wie Auflösung 23, mm × %.1f px/mm (LK-Geländebreite)' % K_24, 'eigene Typen nur für Auflösung 24',
     'TYP hat nur eine Breite je Typ. Zuordnung: D24 in make_typ.py.')

# ---------------------------------------------------------------- Höhenkurven (T62)
def zk(mm_zaehl, mm_normal):
    """Zählkurve: mindestens 1 px breiter als die Normalkurve (bei 1 px Normalkurve sonst gleich)."""
    return max(px(mm_zaehl), px(mm_normal) + 1)

# Review 2 (Benutzer, Vorbild LK-Ausschnitt): eine Farbe je Untergrund, Stärke nach Kurvenart,
# alle durchgezogen. SMV25: elevation_minor = 10 m, elevation_medium = 20 m, elevation_major = 100 m.
# Nachtrag Review 2: Ab Auflösung 22 ist nur die 100-m-Zählkurve kräftig (2 px), 10 und 20 m 1 px in
# aufgehelltem Ton. In 21 (nur noch 100-m-Kurven) alles 1 px in eigenen Typen (Benutzer: grob zu kräftig).
# Standardtypen 0x20–0x22 (Gerät erkennt Höhenlinien) gelten für die nahen Stufen.
def _hell(c, share=0.35):
    h = col(c)
    return ''.join('%02X' % round(int(h[i:i + 2], 16) + (255 - int(h[i:i + 2], 16)) * share) for i in (0, 2, 4))


_HK = (  # Untergrund, Farbe, (10 m, 20 m, 100 m nah), (20 m, 100 m grob), Namen
    ('', 'braun', (0x20, 0x21, 0x22), (None, 0x10f15), ('Höhenkurve', 'Contour'), 'Normalkurve (braun): #D7963C 0,10 mm', 'Zählkurve (braun): #D7963C 0,18 mm'),
    (' Fels', 'fels', (0x10f12, 0x10f00, 0x10f01), (None, 0x10f17), ('Höhenkurve Fels', 'Contour on rock'), 'Normalkurve (schwarz): #3E3E3E 0,08 mm', 'Zählkurve (schwarz): #3E3E3E 0,16 mm'),
    (' Gletscher/See', 'gewaesser', (0x10f13, 0x10f02, 0x10f03), (None, 0x10f19), ('Höhenkurve Gletscher/See', 'Contour on glacier'), 'Normalkurve (blau): #0088D0 0,10 mm', 'Zählkurve (blau): #0088D0 0,18 mm'),
)
for _u, _c, (_t10, _t20, _t100), (_g20, _g100), (_de, _en), _sn, _sz in _HK:
    _en_u = _en.replace('Contour', '')
    line_solid(_t10, (_de + ' 10 m', _en + ' 10 m'), _hell(_c), 1, font='SmallFont', fontcol=C[_c])
    soll('Linie', _t10, _de + ' 10 m', _sn, '1 px, aufgehellt', 'nahe Stufen dezent (Review 2)')
    line_solid(_t20, (_de, _en), _hell(_c), 1, font='SmallFont', fontcol=C[_c])
    soll('Linie', _t20, _de, _sn, '1 px, aufgehellt', 'nahe Stufen dezent (Review 2)')
    line_solid(_t100, ('Zählkurve' + _u, 'Index contour' + _en_u), _c, 2, font='SmallFont', fontcol=C[_c])
    soll('Linie', _t100, 'Zählkurve' + _u, _sz, '2 px', 'einzige kräftige Kurve in 23/24 (Review 2)')
    line_solid(_g100, ('Zählkurve' + _u + ' (grob)', 'Index contour' + _en_u + ' (coarse)'), _c, 1, font='SmallFont', fontcol=C[_c])
    soll('Linie', _g100, 'Zählkurve' + _u + ' (grob)', _sz, '1 px', 'Auflösung 21, nur 100-m-Kurven (Review 2)')

# Übersicht (Auflösung < 22): schmale Varianten, sonst deckt das 2-mm-Band die Karte zu
_lg_ueb = band(2.0 * GRENZE * 6.25 / K / 2)
line_bitmap(0x10f10, ('Landesgrenze (Übersicht)', 'National border (overview)'), 'grenzlinie', 'grenzband', _lg_ueb)
soll('Linie', 0x10f10, 'Landesgrenze Übersicht', 'wie Landesgrenze', '%d px Band' % len(_lg_ueb),
     'Auflösung 16–21: Band verschmälert (LK200/500 generalisiert ebenfalls)')
_kg_ueb = band(1.0 * GRENZE * 6.25 / K / 2)
line_bitmap(0x10f11, ('Kantonsgrenze (Übersicht)', 'Canton border (overview)'), 'grenzlinie', 'grenzband', _kg_ueb)
soll('Linie', 0x10f11, 'Kantonsgrenze Übersicht', 'wie Kantonsgrenze', '%d px Band' % len(_kg_ueb), 'Auflösung 20–21, wie oben')
# ---------------------------------------------------------------- Bauten, Leitungen (T40, T50)
line_solid(0x10f07, ('Mauer', 'Wall'), 'schwarz', px(0.14))
soll('Linie', 0x10f07, 'Mauer', 'Laufbahn/Mauer: #000000 0,14–0,20 mm', '%d px' % px(0.14))
line_bitmap(0x10f08, ('Böschung', 'Embankment'), 'braun', 'none', ['x', 'x...', 'x...'])
soll('Linie', 0x10f08, 'Böschung', 'Böschung: Fläche #D7963C (T51)', '3 px Kamm', 'als Linie mit Kamm, Daten nur als Linie')
line_bitmap(0x10f09, ('Felswand', 'Cliff'), 'fels', 'none', ['x', 'x..', 'x..', 'x..'])
soll('Linie', 0x10f09, 'Felswand', 'Fels (Raster) #3F3F3F', '4 px Kamm', 'eigene Signatur, keine Felszeichnung möglich')
line_solid(0x10f0a, ('Grat', 'Ridge'), 'fels', 1, font='SmallFont')
# Review 3: Felslinien aus swissALTI3D (src/dem/rock_relief.py, Höhenlinien im Fels alle 20 m) mit
# Kamm-Signatur: quer stehende Striche (UseOrientation) zeigen entlang der Falllinie, im steilen Fels
# rücken die Linien zusammen und die Striche überlappen. Annäherung an die LK-Felszeichnung.
_KAMM_LEN = [7, 4, 6, 3, 7, 5, 4, 6, 3, 7, 5]       # Strichlängen in px, unregelmässig
_KAMM_POS = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30]


def kamm(height=7):
    rows = [['.'] * 32 for _ in range(height)]
    for x, n in zip(_KAMM_POS, _KAMM_LEN):
        y0 = (height - n) // 2
        for y in range(y0, y0 + n):
            rows[y][x] = 'x'
    return [''.join(r) for r in rows]


line_bitmap(0x10f1a, ('Felsschraffe', 'Rock hatch'), '7A7A7A', 'none', kamm())
soll('Linie', 0x10f1a, 'Felsschraffe (Lichtseite)', 'FELS (Raster): #3F3F3F', 'Kamm 7 px #7A7A7A',
     'aus DEM erzeugt, Lichtseite heller (Review 3)')
line_bitmap(0x10f1b, ('Felsschraffe Schatten', 'Rock hatch shaded'), 'fels_raster', 'none', kamm())
soll('Linie', 0x10f1b, 'Felsschraffe (Schattenseite)', 'FELS (Raster): #3F3F3F', 'Kamm 7 px', 'aus DEM erzeugt (Review 3)')
line_solid(0x10f0b, ('Staumauer, Damm', 'Dam'), 'grau', 3, 'dunkel', 1)
soll('Linie', 0x10f0b, 'Staumauer (Linie)', 'Staumauer: #CCCCCC, Rand #262626 0,12 mm', '3 + 2×1 px')
line_solid(0x10f0c, ('Arealgrenze grün', 'Park outline'), 'gruen', px(0.12))
soll('Linie', 0x10f0c, 'Arealrand grün', 'Areale T63/T64: Rand #70B446 0,12 mm', '%d px' % px(0.12), 'Garmin-Flächen haben keinen Rand: eigene Linie')
line_solid(0x10f0d, ('Arealgrenze', 'Area outline'), 'dunkel', px(0.12))
soll('Linie', 0x10f0d, 'Arealrand dunkel', 'Areale T60/T61/T64: Rand #262626 0,12 mm', '%d px' % px(0.12), 'wie oben')


# ---------------------------------------------------------------- Flächen
def poly_solid(t, names, fill, font='NoLabel', fontcol=None):
    fill = col(fill)
    w('[_polygon]')
    w('Type=0x%x' % t)
    strings(names, font, fontcol)
    w('Xpm="0 0 2 0"')
    w('"a c %s"' % xc(fill))
    w('"c c %s"' % xc(night_area(fill)))
    w('[end]')
    w('')


def poly_pattern(t, names, fg, bg, tile, font='NoLabel', fontcol=None):
    """tile: Liste gleich langer Strings, wird auf 32x32 gekachelt."""
    fg, bg = col(fg), col(bg)
    th, tw = len(tile), len(tile[0])
    assert 32 % th == 0 and 32 % tw == 0, (t, th, tw)
    rows = [(tile[y % th] * (32 // tw)) for y in range(32)]
    w('[_polygon]')
    w('Type=0x%x' % t)
    strings(names, font, fontcol)
    w('Xpm="32 32 4 1"')
    w('"x c %s"' % xc(fg))
    w('". c %s"' % xc(bg))
    w('"X c %s"' % xc(night(fg)))
    w('"o c %s"' % xc(night_area(bg)))
    for r in rows:
        w('"%s"' % r)
    w('[end]')
    w('')


# Flächenmuster wie bisher mit K_LINE (Musterdichte für Fels/Geröll in Test 2c abgestimmt)
K = K_LINE

# ---------------------------------------------------------------- Flächenmuster aus mm-Werten
def _steps(d_mm):
    """Anzahl Wiederholungen in 32 px für einen Abstand in mm (mind. 1) und die Positionen."""
    n = max(1, int(32 / (d_mm * K) + 0.5))
    return [int(i * 32.0 / n) for i in range(n)]


def grid(dx_mm, dy_mm, dot=1, stagger=False, mark=None):
    """Punktraster wie QGIS-PointPatternFill. dot: Punktgrösse in px; mark: eigene Kleinform."""
    tile = [['.'] * 32 for _ in range(32)]
    ys = _steps(dy_mm)
    xs = _steps(dx_mm)
    shape = mark or [['x'] * dot for _ in range(dot)]
    for yi, y0 in enumerate(ys):
        off = (32 // len(xs)) // 2 if stagger and yi % 2 else 0
        for x0 in xs:
            for dy, row in enumerate(shape):
                for dx, ch in enumerate(row):
                    if ch == 'x':
                        tile[(y0 + dy) % 32][(x0 + off + dx) % 32] = 'x'
    return [''.join(r) for r in tile]


def hatch(dist_mm, angle):
    """Linienschraffur wie QGIS-LinePatternFill (Winkel 0, 45 oder 90 Grad, Linien 1 px)."""
    n = max(1, int(32 / (dist_mm * K) + 0.5))
    period = 32.0 / n
    rows = []
    for y in range(32):
        r = ''
        for x in range(32):
            v = {0: y, 90: x, 45: (x + y)}[angle]
            r += 'x' if (v % period) < 1.0 else '.'
        rows.append(r)
    return rows


def overlay(*tiles):
    return [''.join('x' if any(t[y][x] == 'x' for t in tiles) else '.' for x in range(32)) for y in range(32)]


def poly(t, names, fill, sollw, note='', font='NoLabel', fontcol=None):
    poly_solid(t, names, fill, font, fontcol)
    soll('Fläche', t, names[0], sollw, '#%s' % col(fill), note)


def polyp(t, names, fg, bg, tile, sollw, note='', font='NoLabel', fontcol=None):
    poly_pattern(t, names, fg, bg, tile, font, fontcol)
    soll('Fläche', t, names[0], sollw, 'Muster 32×32 #%s auf %s' % (col(fg), 'transparent' if bg == 'none' else '#' + col(bg)), note)


# Gewässer (T56)
poly(0x3c, ('See gross', 'Large lake'), 'see', 'See (gross): #D2EEFF, Rand #0088D0 0,16 mm', 'ohne Uferlinie (Garmin-Flächen ohne Rand)', 'NormalFont', blau)
poly(0x3d, ('See gross (Übersicht)', 'Large lake'), 'see', 'wie 0x3c', 'Auflösung 12–20 ohne Namen (Teilflächen)')
poly(0x3f, ('See (Übersicht)', 'Lake'), 'see', 'wie 0x3e', 'Auflösung 18–20 ohne Namen (Teilflächen)')
poly(0x3e, ('See', 'Lake'), 'see', 'See: #D2EEFF, Rand #0088D0 0,14–0,16 mm', 'wie oben', 'NormalFont', blau)
poly(0x41, ('Kleiner See, Weiher', 'Pond'), 'see', 'See (klein), Wasserbecken: #D2EEFF, Rand #0088D0 0,12–0,14 mm', 'wie oben', 'SmallFont', blau)
poly(0x48, ('Fluss (Fläche)', 'River area'), 'fluss', 'Fluss: #9CD5F8, Rand #0088D0 0,12 mm', 'wie oben', 'SmallFont', blau)
polyp(0x4c, ('See mit wechselndem Wasserstand', 'Intermittent lake'), 'gewaesser', 'see',
      overlay(hatch(1.2, 0), [['.'] * 32 for _ in range(32)]),
      'See (wechselnder Wasserstand): #D2EEFF, Rand #0088D0 0,18 mm', 'eigene Kennzeichnung durch Linien', 'SmallFont', blau)
poly(0x11004, ('Schwimmbecken', 'Swimming pool'), 'gewaesser', 'Schwimmbecken: #0088D0')

# Bodenbedeckung (T65, T43-Symbole)
poly(0x50, ('Wald', 'Forest'), 'wald', 'Wald: #CDE6BE', '', 'SmallFont', C['gruen'])
polyp(0x11000, ('Wald offen', 'Open forest'), 'gruen', 'none', grid(1.0, 1.0, dot=2, stagger=True),
      'offener Wald: Symbole #70B446 0,38–0,44 mm', 'Symbolpunkte aus den Daten → regelmässiges Muster (Abstand geschätzt 1,0 mm)')
polyp(0x4f, ('Gebüschwald', 'Scrub'), 'gruen', 'none', grid(0.7, 0.7, dot=1, stagger=True),
      'Gebüschwald: Symbole #70B446 0,25–0,42 mm', 'wie offener Wald (Abstand geschätzt 0,7 mm)')
polyp(0x51, ('Feuchtgebiet', 'Wetland'), 'gewaesser', 'none',
      grid(1.6, 0.8, stagger=True, mark=[list('xxxxx')]),
      'Feuchtgebiet: Symbol #0088D0 1,0 mm (waagrechte Striche)', 'Symbol als 5-px-Strich im versetzten Raster')
# Fels, Geröll, Gletscher sind in SMV Rasterzeichnungen (#3F3F3F bzw. #006BC7 auf transparent)
# Etappe 6: lockerer (BaseCamp-Test 2b: durchgehende Schraffur zu dunkel, verdeckt Wege und Namen).
# Review 3 (Säntis): Fels mit 3 % Deckung war praktisch unsichtbar. Jetzt unregelmässig gestreute
# Felsstriche (steil, 3–4 px) mit ca. 9 % Deckung, Geröll als gestreute Punkte mit ca. 6 % Deckung.
# Die eigentliche Felszeichnung liefern die Felsschraffen aus dem DEM (0x10f1a/0x10f1b).
import random as _random


def scatter(n, marks, min_dist, seed):
    """32×32-Kachel mit n gestreuten Kleinformen (nahtlos wiederholbar), Mindestabstand in px."""
    rnd = _random.Random(seed)
    tile = [['.'] * 32 for _ in range(32)]
    placed = []
    tries = 0
    while len(placed) < n and tries < 20000:
        tries += 1
        x, y = rnd.randrange(32), rnd.randrange(32)
        if any(min(abs(x - a), 32 - abs(x - a)) ** 2 + min(abs(y - b), 32 - abs(y - b)) ** 2 < min_dist ** 2
               for a, b in placed):
            continue
        placed.append((x, y))
        for dx, dy in marks[len(placed) % len(marks)]:
            tile[(y + dy) % 32][(x + dx) % 32] = 'x'
    return [''.join(r) for r in tile]


def coverage(tile):
    return sum(r.count('x') for r in tile) / 1024.0


_FELS_MARKS = [[(0, 0), (0, 1), (1, 2), (1, 3)], [(1, 0), (1, 1), (0, 2)], [(0, 0), (1, 1), (1, 2), (2, 3)]]
_fels = scatter(28, _FELS_MARKS, 5, 7701)
polyp(0x11001, ('Fels', 'Rock'), 'fels_raster', 'none', _fels,
      'FELS (Raster): #3F3F3F auf transparent',
      'Felszeichnung nach Gelände nur über die DEM-Schraffen: gestreute Striche, %.0f %% Deckung (Review 3)' % (100 * coverage(_fels)))
_geroell = scatter(60, [[(0, 0)]], 3, 7702)
polyp(0x11002, ('Geröll', 'Scree'), 'fels_raster', 'none', _geroell,
      'GEROELL (Raster): #3F3F3F Punkte auf transparent',
      'gestreute Punkte, %.0f %% Deckung (Review 3)' % (100 * coverage(_geroell)))

# Review 3: Schattenflächen aus swissALTI3D (src/dem/rock_relief.py) verstärken die graue
# Garmin-Schummerung auf steilen Schattenhängen. Geordnetes Raster (Bayer 4×4) in Blaugrau auf
# transparent: „mittel“ 2/16, „stark“ weitere 2/16 (stark liegt immer in mittel, zusammen 25 %).
_BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def bayer(lo, hi):
    return [''.join('x' if lo <= _BAYER[y % 4][x % 4] < hi else '.' for x in range(32)) for y in range(32)]


C['schatten'] = '50647D'
polyp(0x11010, ('Schatten', 'Shade'), 'schatten', 'none', bayer(0, 2),
      'Schummerung (Raster, kräftig im Gebirge)', 'zusätzlich zur Garmin-Schummerung: Raster 12,5 %% #%s (Review 3)' % C['schatten'])
polyp(0x11011, ('Schatten stark', 'Deep shade'), 'schatten', 'none', bayer(2, 4),
      'Schummerung (Raster, kräftig im Gebirge)', 'wie 0x11010, zusätzlich 12,5 % (zusammen 25 %)')
polyp(0x4d, ('Gletscher', 'Glacier'), 'gletscher_raster', 'none',
      grid(2.4, 1.0, stagger=True, mark=[list('xxxxxx')]),
      'GLETSCHER (Raster): #006BC7 Linien auf transparent', 'Linien nach Gelände nicht möglich: kurze Striche', 'NormalFont', blau)

# Nutzungs- und Freizeitareale (T64, T63)
polyp(0x11006, ('Reben', 'Vineyard'), 'gruen', 'none', grid(0.6, 1.8, mark=[['x']] * 4),
      'Reben: Symbol #70B446 im Raster 0,6 × 1,8 mm', 'Rebsymbol als 4-px-Senkrechtstrich')
polyp(0x4e, ('Obstanlage', 'Orchard'), 'gruen', 'none',
      grid(0.8, 0.8, mark=[list('.x.'), list('xxx'), list('.x.')]),
      'Obstanlage: Kreis #70B446 0,24 mm im Raster 0,8 mm', 'Kreis als 3-px-Kreuz')
polyp(0x11007, ('Baumschule', 'Plant nursery'), 'gruen', 'none', grid(0.7, 0.7, dot=1),
      'Baumschule: Kreis #70B446 0,20 mm im Raster 0,7 mm')
poly(0x1a, ('Friedhof', 'Cemetery'), 'areal', 'Friedhof: #E7F3E1, Rand #70B446 0,12 mm', 'Rand als Linie 0x10f0c', 'SmallFont')
poly(0x17, ('Park, Schrebergarten', 'Park'), 'areal', 'Öffentliches Parkareal, Schrebergarten: #E7F3E1, Rand #70B446', 'Rand als Linie', 'SmallFont')
poly(0x11005, ('Deponie, Abbau', 'Landfill, quarry'), 'deponie', 'Deponieareal: #F0DABC', '', 'SmallFont')
poly(0x0b, ('Spitalareal', 'Hospital'), 'spital', 'Spitalareal: #F2F2F2', '', 'SmallFont')
poly(0x0c, ('Unterwerk, Kraftwerk', 'Substation'), 'weiss', 'Unterwerkareal: #FFFFFF, Rand #262626', 'Rand als Linie 0x10f0d')
poly(0x11003, ('Campingplatz', 'Camp site'), 'areal', 'Campingplatzareal: #E7F3E1, Rand #70B446', 'Rand als Linie', 'SmallFont')
poly(0x18, ('Golfplatz', 'Golf course'), 'areal', 'Golfplatzareal: #E7F3E1, Rand #70B446', 'Rand als Linie', 'SmallFont')

# Verkehrsareale (T61) und Bauten-Flächen (T60)
poly(0x05, ('Parkplatz', 'Parking'), 'weiss', 'Parkplatzareal: #FFFFFF, Rand #262626 0,12 mm', 'Rand als Linie 0x10f0d')
poly(0x1100a, ('Verkehrsfläche', 'Traffic area'), 'weiss', 'Verkehrsfläche: #FFFFFF (Autobahn #FBBF39, Durchgang #F5AE95, Verbindung #FFF582)',
     'nur weiss, weil die Verkehrsbedeutung im Tag-Schema fehlt')
poly(0x19, ('Sportplatz', 'Sports field'), 'areal', 'Sportplatz: #E7F3E1, Rand #262626 0,12 mm', 'Rand grün statt dunkel (gemeinsame Randlinie)', 'SmallFont')
poly(0x0e, ('Hartbelagpiste', 'Paved runway'), 'weiss', 'Hartbelagpiste: #FFFFFF, Rand #262626')
poly(0x11008, ('Graspiste', 'Grass runway'), 'areal', 'Graspiste: #E7F3E1, Rand #262626')
polyp(0x1100b, ('Solaranlage', 'Solar panels'), 'schwarz', 'solar', overlay(hatch(0.8, 90), hatch(0.6, 0)),
      'Solarpanel: #FFFF9B, Linien #000000 0,8 mm senkrecht und 0,6 mm waagrecht')
poly(0x1100d, ('Brücke, Staudamm', 'Bridge, dam'), 'grau', 'Staumauer, Staudamm: #CCCCCC, Rand #262626')

# Gebäude (T48)
poly(0x13, ('Gebäude', 'Building'), 'schwarz', 'Gebäude, Mauer gross, Wehr: #000000')
soll('Fläche', 0x13, 'Gebäudeecken', 'TLM-Grundriss rechtwinklig (Abweichung im Median 0,1°)',
     'Ecken auf das Raster der Auflösung 24 gerundet (1,6 m × 2,4 m), Abweichung im Median 4,8°, 10 % über 22°',
     'Garmin-Grenze (IMG kennt kein feineres Raster). Offen: Ausrichtung je Gebäudegruppe vor dem Runden '
     '(Prototyp Niederuzwil: Median 1,3°, im Ortskern 0,0°), Umsetzung in vector-convert')
polyp(0x1100c, ('Flugdach, Treibhaus', 'Roof, greenhouse'), 'schwarz', 'weiss', hatch(0.4, 45),
      'Flugdach, Treibhaus: #FFFFFF, Schraffur 45° #000000 alle 0,4 mm, Rand #333333', 'ohne Rand')

# Kartenhintergrund: mkgmap legt je Kachel eine Fläche 0x4b an; ohne TYP-Eintrag zeigt BaseCamp Creme.
poly(0x4b, ('Hintergrund', 'Background'), 'weiss', 'Kartengrund #FFFFFF (LK: weisses Papier)')

# Nicht in SMV25: nur für die Übersichtsstufen
poly(0x11009, ('Flugplatzareal', 'Aerodrome'), 'F5F5F5', '– (nicht in SMV25)', 'eigene Fläche für die Übersicht', 'SmallFont')
poly(0x1100e, ('Siedlung (Übersicht)', 'Settlement'), 'siedlung', '– (nicht in SMV25)', 'Auflösung 14–21, #BEBEBE (Test 20: #DADADA zu blass)', 'NormalFont')
poly(0x1100f, ('Siedlung (LK50)', 'Settlement'), 'F0F0F0', '– (nicht in SMV25)', 'Auflösung 22, sehr hell unter den Gebäuden (Test 10)')

# Zeichenreihenfolge nach der Layerfolge im SMV25-QGIS-Projekt (unten → oben):
# KOMB, T65 Bodenbedeckung, T64 Nutzungsareal, T63 Freizeitareal, T61 Verkehrsareal,
# T60 Baute_ply, GEROELL, FELS, T56 Gewässer, … T43 Bodenbedeckung-Symbole …, T48 Gebäude, GLETSCHER.
# Linien zeichnet Garmin immer über allen Flächen.
DRAW_ORDER = [
    (1, [0x4b]),  # Hintergrund allein (Review 2: auf gleicher Stufe deckte er je Subdivision die Siedlung zu)
    (2, [0x1100e, 0x1100f, 0x11009]),                                 # Siedlung, Flugplatz, nicht SMV
    (3, [0x50]),                                                      # T65
    (4, [0x1a, 0x17, 0x11005, 0x0b, 0x0c, 0x11006, 0x4e, 0x11007,     # T64
         0x11003, 0x18]),                                             # T63
    (5, [0x05, 0x1100a]),                                             # T61
    (6, [0x19, 0x0e, 0x11008, 0x1100b, 0x11004, 0x1100d]),            # T60
    (7, [0x11002, 0x11001]),                                          # GEROELL, FELS
    (8, [0x3c, 0x3d, 0x3e, 0x3f, 0x41, 0x48, 0x4c]),                              # T56
    (9, [0x11000, 0x4f, 0x51, 0x11010, 0x11011]),                     # T43, Schatten (Review 3)
    (10, [0x13, 0x1100c, 0x4d]),                                       # T48, GLETSCHER
]

# ---------------------------------------------------------------- Punkte
PAL = {'k': 'schwarz', 'w': 'weiss', 'r': 'bahn', 'b': 'gewaesser', 'g': 'gruen', 'n': 'braun',
       'd': 'fels', 'y': 'autobahn', 's': 'seil', 'm': 'grenzlinie'}


# Soll-Grössen der SMV-Symbole (FontMarker-Grösse in mm, T29–T39). Die Schriftgrösse ist die
# Geviert-Höhe; das sichtbare Zeichen ist etwas kleiner. Ist = Höhe der eigenen Pixelgrafik.
POI_SOLL = {
    0x6616: ('Gipfel: Höhenkote #000000 0,8 mm mit weissem Rand 1,1 mm (T38) + Name', 1.1),
    0x6300: ('Höhenkote: Punkt #000000 0,35 mm, weisser Rand 0,5 mm', 0.5),
    0x1150f: ('Höhenkote: Punkt #000000 0,35 mm, weisser Rand 0,5 mm', 0.5),
    0x11510: ('Gipfelkote Klassen 1 und 2: Punkt #000000 0,35 mm, weisser Rand 0,5 mm', 0.5),
    0x6601: ('Grotte, Höhle #000000', 0.9),
    0x6614: ('Felsblock #3E3E3E', 0.55),
    0x6511: ('Quelle #0088D0', 0.9),
    0x5000: ('Brunnen #0088D0 auf #E6F2FF', 0.8),
    0x11503: ('Gipfelkreuz #000000', 1.3),
    0x2c0b: ('Kapelle #000000', 0.9),
    0x6404: ('Sakraler Turm #000000', 1.2),
    0x11504: ('Bildstock #000000', 1.3),
    0x11505: ('Denkmal #000000', 1.0),
    0x2c04: ('Aussichtsturm #000000', 1.4),
    0x11501: ('Antenne gross #000000', 2.044),
    0x11507: ('Wasserturm #0088D0', 0.92),
    0x11506: ('Hochkamin #000000', 1.1),
    0x6411: ('Turm #000000', 0.8),
    0x11502: ('Windturbine #000000', 1.94),
    0x11508: ('Triangulationspyramide #000000', 1.2),
    0x2b03: ('Campingplatz #000000', 2.0),
    0x2a00: ('Gastgewerbe abgelegen (Fahne) #000000', 1.17),
    0x5904: ('Heliport #000000', 2.1),
    0x1150a: ('Durchfahrtssperre #DD1919', 0.45),
    0x1150b: ('Landesgrenzstein #C22976', 0.5),
    0x1150c: ('Einzelbaum #70B446', 0.44),
    0x3002: ('Spitalareal-Symbol #0088D0', 1.5),
}


# Symbole in SMV-Sollgrösse (Etappe 3). Ersetzen die älteren, kleineren Entwürfe weiter unten.
LK_ART = {
    0x6616: [  # Gipfel: wie LK Höhenkote 0,8 mm mit weissem Freistellrand (kein Dreieck)
        '.wwwww.',
        'wwkkkww',
        'wkkkkkw',
        'wkkkkkw',
        'wkkkkkw',
        'wwkkkww',
        '.wwwww.'],
    0x6300: [
        'wwww',
        'wkkw',
        'wkkw',
        'wwww'],
    0x11503: [
        '...k...',
        '...k...',
        'kkkkkkk',
        '...k...',
        '...k...',
        '...k...',
        '...k...',
        '..kkk..'],
    0x11504: [
        '.kkk.',
        '.kwk.',
        '.kkk.',
        '..k..',
        '..k..',
        '..k..',
        '..k..',
        'kkkkk'],
    0x11501: [
        'k.....k',
        '.k...k.',
        '..kkk..',
        '...k...',
        '..kkk..',
        '...k...',
        '..k.k..',
        '..k.k..',
        '.k...k.',
        '.k...k.',
        'kkkkkkk'],
    0x11502: [
        '....k....',
        '....k....',
        '....k....',
        '....k....',
        '...kkk...',
        '..k.k.k..',
        '.k..k..k.',
        'k...k...k',
        '....k....',
        '....k....',
        '...kkk...'],
    0x11506: [
        '.kkk.',
        '.kkk.',
        '.kkk.',
        '.kkk.',
        'kkkkk',
        'kkkkk',
        'kkkkk'],
    0x11508: [
        '...k...',
        '..k.k..',
        '..k.k..',
        '.k.k.k.',
        '.k...k.',
        'kkkkkkk'],
    0x2b03: [
        '.....k.....',
        '....kkk....',
        '...kk.kk...',
        '..kk...kk..',
        '.kk..k..kk.',
        'kk..kkk..kk',
        'kkkkkkkkkkk'],
    0x5904: [
        '...kkkkk...',
        '..kwwwwwk..',
        '.kwkwwwkwk.',
        'kwwkwwwkwwk',
        'kwwkkkkkwwk',
        'kwwkwwwkwwk',
        'kwwkwwwkwwk',
        '.kwkwwwkwk.',
        '..kwwwwwk..',
        '...kkkkk...'],
    0x2c04: [
        'k.......k',
        '.k.....k.',
        '..kkkkk..',
        '..kwwwk..',
        '..kwkwk..',
        '..kwwwk..',
        '..kkkkk..',
        '.k.....k.',
        'k.......k'],
    0x3002: [
        'bbbbbbbbb',
        'bbbbwbbbb',
        'bbbbwbbbb',
        'bbbbwbbbb',
        'bwwwwwwwb',
        'bbbbwbbbb',
        'bbbbwbbbb',
        'bbbbwbbbb',
        'bbbbbbbbb'],
}


# Review 1: POIs, deren Namen man sucht und liest, mit NormalFont. Kleinobjekte (Baum, Grenzstein,
# Bildstock, Brunnen …) bleiben SmallFont, damit die Karte nicht überladen wirkt.
NORMAL_POI = {0x6601, 0x2c02, 0x2c04, 0x5200, 0x2b03, 0x2a00, 0x2f08,
              0x5902, 0x5904, 0x3002, 0x2c0b, 0x6404, 0x6508}


# Gerätetest 7794-klassen5 (Benutzer): POI-Symbole am GPSMAP 67 zu klein. Vergrössert werden nur POIs
# (Ziele und Dienste), nicht die Kartenzeichen der LK wie Baum, Poller, Grenzstein, Brunnen, Bildstock,
# Kreuz, Turm oder Pass (Benutzer: ausschliesslich POI). Symbole bis 7 px werden verdoppelt, 8–10 px
# × 1,5 (nächster Nachbar), ab 11 px bleiben sie. Der Bahnhof hat ein eigenes Symbol 15×9.
SCALE_POI = {0x2b04, 0x2b03, 0x2a00, 0x3002, 0x5902, 0x5904, 0x5200, 0x2c04, 0x2c02, 0x6404, 0x2c0b,
             0x6601, 0x6508}


def scale_art(art, f):
    h, wd = len(art), len(art[0])
    nh, nw = int(h * f + 0.5), int(wd * f + 0.5)
    return [''.join(art[min(h - 1, int(y / f))][min(wd - 1, int(x / f))] for x in range(nw)) for y in range(nh)]


def poi(t, names, art, font='SmallFont', fontcol=None, soll_txt=None):
    """art: Liste gleich langer Strings; '.' transparent, sonst Schlüssel aus PAL."""
    art = LK_ART.get(t, art)
    if t in SCALE_POI and art != ['.']:
        m = max(len(art), len(art[0]))
        if m <= 7:
            art = scale_art(art, 2)
        elif m <= 10:
            art = scale_art(art, 1.5)
    h, wd = len(art), len(art[0])
    if t in NORMAL_POI and font == 'SmallFont':
        font = 'NormalFont'  # Review 1: POI-Beschriftungen zu klein
    if t in POI_SOLL:
        txt, mm = POI_SOLL[t]
        target = max(1, int(mm * K_SYM + 0.5))
        if abs(h - target) <= 1:
            note = 'Grösse passt'
        elif h < target and mm >= 1.5:
            note = '%+d px: SMV-Grösse ist die Geviert-Höhe der Symbolschrift, das Zeichen selbst ist kleiner' % (h - target)
        else:
            note = '%+d px gegenüber Soll, eigenes Pixelsymbol' % (h - target)
        soll('Punkt', t, names[0], '%s, %.2f mm = %d px' % (txt, mm, target), '%d×%d px' % (wd, h), note)
    elif soll_txt:
        soll('Punkt', t, names[0], soll_txt[0], '%d×%d px' % (wd, h), soll_txt[1])
    elif art != ['.']:
        soll('Punkt', t, names[0], '– (nicht in SMV25 oder Symbol aus Areal)', '%d×%d px' % (wd, h), 'eigenes Symbol')
    elif font == 'NoLabel':
        soll('Punkt', t, names[0], 'Name in der Suche', 'unsichtbar (ohne Symbol und Schrift)',
             'nur Suchpunkt, damit er gleichnamige Beschriftungen nicht verdeckt')
    else:
        soll('Punkt', t, names[0], 'Beschriftung ohne Symbol', 'nur Schrift (%s%s)' % (font, ', ' + '#' + fontcol if fontcol else ''),
             'Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe)')
    assert all(len(r) == wd for r in art), hex(t)
    used = sorted({ch for r in art for ch in r if ch != '.'})
    w('[_point]')
    w('Type=0x%x' % t)
    strings(names, font, fontcol)
    for label, fn in (('DayXpm', lambda h_: h_), ('NightXpm', night)):
        w('%s="%d %d %d 1"' % (label, wd, h, len(used) + 1))
        for ch in used:
            c = col(PAL[ch])
            if label == 'NightXpm' and ch == 'w':
                c = '202020'
            else:
                c = fn(c) if label == 'NightXpm' and ch not in 'rbgnym' else c
            w('"%s c #%s"' % (ch, c))
        w('". c none"')
        for r in art:
            w('"%s"' % r)
    w('[end]')
    w('')


def label_only(t, names, font, fontcol=None):
    poi(t, names, ['.'], font, fontcol)


# Orte: nur Schrift wie in der LK
# Stadt, Kleinstadt, Dorf (0x0400, 0x0800, 0x0c00): bewusst KEIN TYP-Eintrag (Test 11). Garmin
# zeichnet City-Typen mit eigener Logik (Zoomschwelle je Typ, Schriftgrösse, Ortspunkt); ein
# TYP-Override mit transparentem 1×1-Symbol führte in BaseCamp dazu, dass „ST. GALLEN“ und
# „HERISAU“ nicht gezeichnet wurden. Wie die mkgmap-Referenz-TYP mapnik.txt. Weiler, Quartiere und
# Einzelhöfe bleiben reine Schrift (LK ohne Ortspunkt).
soll('Punkt', 0x0400, 'Stadt, Kleinstadt, Dorf (0x0400/0x0800/0x0c00)', 'LK: Ortsname ohne Punkt, Städte in Grossbuchstaben',
     'Garmin-Standarddarstellung (kein TYP-Eintrag)', 'Abweichung: Garmin zeichnet einen Ortspunkt. Mit TYP-Override zeigte BaseCamp die Namen nicht.')
label_only(0x0e00, ('Weiler', 'Hamlet'), 'LargeFont')
label_only(0x0f00, ('Quartier', 'Suburb'), 'LargeFont')  # LK: Quartiernamen wie Ortsnamen
label_only(0x6613, ('Grat', 'Ridge'), 'SmallFont')
label_only(0x6402, ('Gebäudename', 'Building name'), 'NormalFont')  # LK 6,0 pt ≈ 15 px
label_only(0x2000, ('Autobahnausfahrt', 'Motorway exit'), 'SmallFont')
label_only(0x1100, ('Einzelhof', 'Farm'), 'NormalFont')
label_only(0x2800, ('Flurname', 'Locality'), 'NormalFont')  # LK 5,7 pt ≈ 16 px
label_only(0x6602, ('Gebietsname', 'Area name'), 'LargeFont')  # LK 6,8–7,3 pt ≈ 17–18 px
label_only(0x6617, ('Talname', 'Valley'), 'LargeFont')
label_only(0x6611, ('Gebirge', 'Mountain range'), 'LargeFont')
# Massiv mit Hauptgipfel: Suchpunkt am höchsten Gipfel, ohne Symbol und ohne Schrift. Mit 0x6616
# liess BaseCamp die überdeckte Gipfelschrift weg (Säntis ohne Name und Höhe, Befund 2026-11-07).
poi(0x6612, ('Massiv', 'Massif'), ['.'], 'NoLabel')
label_only(0x650a, ('Gletschername', 'Glacier name'), 'NormalFont', blau)
label_only(0x650d, ('Seename', 'Lake name'), 'NormalFont', blau)
# Offene Abweichungen aus dem Gerätetest 7794-klassen3 (GPSMAP 67, Raum Säntis), nicht weiter verfolgt
soll('Punkt', 0x650a, 'Gletschername am Säntis (Blauschnee)', 'LK100: Gletschername ab 1:100 000',
     'am GPSMAP 67 erst unter 300 m sichtbar', 'offen: Ursache nicht geprüft, am Säntis liegen viele Labels')
soll('Punkt', 0x6602, 'Landschaftsname Toggenburg', 'LK200: Landschaftsname ab 1:200 000',
     'am GPSMAP 67 auf keiner Zoomstufe sichtbar', 'offen: Ursache nicht geprüft')

poi(0x6616, ('Gipfel', 'Summit'), [
    '...www...',
    '..wwkww..',
    '..wkkkw..',
    '.wkkkkkw.',
    '.wkkkkkw.',
    'wkkkkkkkw',
    'wwwwwwwww'], 'NormalFont')
poi(0x6300, ('Höhenkote', 'Spot height'), [
    '.www.',
    'wkkkw',
    'wkkkw',
    'wkkkw',
    '.www.'], 'NormalFont')  # Kotenzahl LK ≈ 17 px (style-qa)
# Höhenkote als erweiterter Typ (Label in Metern, wie LK), gleiche Grafik wie 0x6300
poi(0x1150f, ('Höhenkote', 'Spot height'), [
    'wwww',
    'wkkw',
    'wkkw',
    'wwww'], 'NormalFont')
# Gipfelkote der Gipfelklassen 1 und 2 (SMV1000, SMV500): gleiche Grafik, Zahl in LargeFont
poi(0x11510, ('Gipfelkote', 'Summit height'), [
    'wwww',
    'wkkw',
    'wkkw',
    'wwww'], 'LargeFont')
# Ortsnamen-Beschriftung in Auflösung 22–24 (zusätzlich zum City-Punkt), nur Schrift
# Variante (Test 14): BaseCamp verwirft offenbar Punkte mit völlig transparentem Symbol.
#   --ort-variante a: Standardtyp „Label“ mit Untertypen 0x2801 (Stadt) / 0x2802 (Dorf), nur Schrift
#   --ort-variante b (Standard): 0x1150d / 0x1150e mit 1×1-Symbol in Weiss (sichtbar, unauffällig)
# Etappe 22 (fest): Standard d2 = 4×4-Ortsring mit LargeFont (D1/D2: 1×1-Symbole verwirft BaseCamp).
ORT_VARIANTE = sys.argv[sys.argv.index('--ort-variante') + 1] if '--ort-variante' in sys.argv else 'd2'
#   --ort-variante d1 / d2: 0x1150d / 0x1150e mit 4×4-Ortsring (wie LK-Ortssignatur), NormalFont / LargeFont
ORTSRING = ['.kk.', 'k..k', 'k..k', '.kk.']
if ORT_VARIANTE == 'a':
    label_only(0x2801, ('Ortsname', 'Town name'), 'LargeFont')
    label_only(0x2802, ('Dorfname', 'Village name'), 'LargeFont')
elif ORT_VARIANTE in ('d1', 'd2'):
    _f = 'NormalFont' if ORT_VARIANTE == 'd1' else 'LargeFont'
    poi(0x1150d, ('Ortsname', 'Town name'), ORTSRING, _f)
    # Dörfer eine Schriftklasse kleiner als Städte (Test 16: Städte kaum grösser als Dörfer)
    poi(0x1150e, ('Dorfname', 'Village name'), ORTSRING, 'NormalFont')
else:
    poi(0x1150d, ('Ortsname', 'Town name'), ['w'], 'LargeFont')
    poi(0x1150e, ('Dorfname', 'Village name'), ['w'], 'LargeFont')
poi(0x660b, ('Pass, Sattel', 'Pass'), [
    'k.....k',
    '.k...k.',
    '.k...k.',
    '.k...k.',
    'k.....k'], 'NormalFont')
poi(0x6601, ('Höhle', 'Cave'), [  # Review 1: grösser (vorher 7×5, nur mit Lupe zu finden)
    '...kkkkk...',
    '.kkkkkkkkk.',
    'kkkkkkkkkkk',
    'kkkkwwwkkkk',
    'kkkwwwwwkkk',
    'kkwwwwwwwkk',
    'kkwwwwwwwkk',
    'kkwwwwwwwkk'])
poi(0x6614, ('Felsblock', 'Boulder'), [
    '.ddd.',
    'ddddd',
    'ddddd',
    '.ddd.'])
poi(0x6511, ('Quelle', 'Spring'), [
    '.bbb.....',
    'b...b....',
    'b...bbbbb',
    'b...b....',
    '.bbb.....'])
poi(0x6508, ('Wasserfall', 'Waterfall'), [
    'bbbbbbb',
    '..b.b..',
    '.b.b.b.',
    '..b.b..',
    '.b.b.b.'])
poi(0x5000, ('Brunnen', 'Drinking water'), [
    '.www.',
    'wbbbw',
    'wbwbw',
    'wbbbw',
    '.www.'])
poi(0x11503, ('Gipfelkreuz', 'Summit cross'), [
    '..k..',
    'kkkkk',
    '..k..',
    '..k..',
    '..k..',
    '..k..'])
poi(0x2c0b, ('Kapelle', 'Chapel'), [
    '..k..',
    '.kkk.',
    '..k..',
    'kkkkk',
    'kkkkk',
    'kkkkk'])
poi(0x6404, ('Kirche', 'Church'), [
    '...k...',
    '..kkk..',
    '...k...',
    '.kkkkk.',
    'kkwwwkk',
    'kkwwwkk',
    '.kkkkk.'])
poi(0x11504, ('Bildstock', 'Wayside shrine'), [
    'kkk',
    'kkk',
    '.k.',
    '.k.'])
poi(0x11505, ('Denkmal', 'Memorial'), [
    '..k..',
    '.kkk.',
    '.kkk.',
    '.kkk.',
    'kkkkk'])
poi(0x2c02, ('Burg, Ruine', 'Castle, ruins'), [  # Review 1: grösser, mit Zinnen und Tor
    'k.k.k.k.k',
    'kkkkkkkkk',
    '.kwwwwwk.',
    '.kwwwwwk.',
    '.kwwkwwk.',
    '.kwkkkwk.',
    '.kwkkkwk.',
    '.kwkkkwk.',
    '.kkkkkkk.'])
poi(0x2c04, ('Aussichtsturm', 'Observation tower'), [
    'k.....k',
    '.kkkkk.',
    '.kwwwk.',
    '.kwkwk.',
    '.kwwwk.',
    '.kkkkk.',
    'k.....k'])
poi(0x11501, ('Antenne', 'Antenna'), [
    'k.k.k',
    '.kkk.',
    '..k..',
    '..k..',
    '.kkk.'])
poi(0x11507, ('Wasserturm', 'Water tower'), [
    '.bbb.',
    'bwwwb',
    'bwbwb',
    'bwwwb',
    '.bbb.'])
poi(0x11506, ('Hochkamin', 'Chimney'), [
    '.kkk.',
    'kkkkk',
    'kkkkk',
    '.kkk.'])
poi(0x6411, ('Turm', 'Tower'), [
    '.kkk.',
    'kwwwk',
    'kwkwk',
    'kwwwk',
    '.kkk.'])
poi(0x11502, ('Windturbine', 'Wind turbine'), [
    'k...k',
    '.k.k.',
    '..k..',
    '..k..',
    '..k..',
    '.kkk.'])
poi(0x11508, ('Triangulationspunkt', 'Survey point'), [
    '..k..',
    '.k.k.',
    'k.k.k',
    'kkkkk'])
poi(0x5200, ('Aussichtspunkt', 'Viewpoint'), [
    'k..k..k',
    '.k.k.k.',
    '.......',
    '..kkk..',
    '.kkkkk.'])
poi(0x2b04, ('Berghütte', 'Mountain hut'), [
    '....k....',
    '...kkk...',
    '..kkkkk..',
    '.kkkkkkk.',
    'kkkkkkkkk',
    '.kkkwkkk.',
    '.kkkwkkk.'], 'NormalFont')
poi(0x2b03, ('Camping', 'Camp site'), [
    '...k...',
    '..kkk..',
    '.kk.kk.',
    'kk...kk',
    'kkkkkkk'])
poi(0x2a00, ('Gastwirtschaft', 'Restaurant'), [  # Review 1: Besteck statt Fahne (Fahne zu klein)
    'kkkkkkkkkkk',
    'kwkwkwwwkwk',
    'kwkwkwwkkwk',
    'kwkwkwwkkwk',
    'kwkkkwwkkwk',
    'kwwkwwwkkwk',
    'kwwkwwwwkwk',
    'kwwkwwwwkwk',
    'kwwkwwwwkwk',
    'kwwkwwwwkwk',
    'kkkkkkkkkkk'])
# Bahnhof: rotes Symbol 15×9 (Gerätetest 7794-klassen5: grösser), Name ab 24. Die Schriftfarbe #DD1919
# (Rot der Bahnlinien, Wunsch des Benutzers) steht in der TYP, das GPSMAP 67 zeichnet Punktnamen aber
# immer schwarz (Farbtest FID 7799: alle Farben, Schriftgrössen und Typarten).
poi(0x2f08, ('Bahnhof', 'Railway station'), [
    'wwwwwwwwwwwwwww',
    'wrrrrrrrrrrrrrw',
    'wrrrrrrrrrrrrrw',
    'wrrrrrrrrrrrrrw',
    'wrrrrrrrrrrrrrw',
    'wrrrrrrrrrrrrrw',
    'wrrrrrrrrrrrrrw',
    'wrrrrrrrrrrrrrw',
    'wwwwwwwwwwwwwww'], 'NormalFont', C['bahn'],
    soll_txt=('Name rot (Wunsch des Benutzers), Rot #DD1919 der Bahnlinien. SMV25 hat kein Bahnhofsymbol',
              'Symbol rot 15×9, Name ab 24. Schrift #DD1919 in der TYP, das GPSMAP 67 zeichnet Punktnamen immer '
              'schwarz (belegt mit Farbtest FID 7799). Bus, Schiff und Seilbahn nur im Routen-Overlay'))
# Seilbahn-, Bus- und Schiffshaltestellen stehen im Routen-Overlay (eigene TYP), nicht hier.
poi(0x5902, ('Flugplatz', 'Airfield'), [
    '...k...',
    '...k...',
    'kkkkkkk',
    '...k...',
    '..kkk..'])
poi(0x5904, ('Heliport', 'Heliport'), [
    '.kkkkk.',
    'kwkwkwk',
    'kwkkkwk',
    'kwkwkwk',
    '.kkkkk.'])
poi(0x1150c, ('Einzelbaum', 'Tree'), [
    '.g.',
    'ggg',
    '.g.'])
poi(0x1150b, ('Landesgrenzstein', 'Boundary stone'), [
    'mmm',
    'mmm',
    'mmm'])
poi(0x1150a, ('Durchfahrtssperre', 'Barrier'), [
    'rrrrr',
    'rrrrr'])
poi(0x3002, ('Spital', 'Hospital'), [
    'bbbbbbb',
    'bbbwbbb',
    'bbbwbbb',
    'bwwwwwb',
    'bbbwbbb',
    'bbbwbbb',
    'bbbbbbb'])

# ---------------------------------------------------------------- Kopf und Ausgabe
head = [
    '; -*- coding: utf-8 -*-',
    '; Helvetopo – TYP-Quelle (mkgmap-TYP-Textformat), erzeugt von src/style/tools/make_typ.py.',
    '; Nicht von Hand ändern, sondern das Skript anpassen und neu erzeugen.',
    '; Farben nach Swiss Map Vector 25 (swisstopo, OGD). Eigene Symbole, keine swisstopo-Logos.',
    '; Daten der Karte: ©swisstopo',
    '',
    '[_id]',
    'FID=7701',
    'ProductCode=1',
    'CodePage=1252',
    '[end]',
    '',
    '[_drawOrder]',
]
for lvl, types in DRAW_ORDER:
    for t in types:
        head.append('Type=0x%x,%d' % (t, lvl))
head += ['[end]', '']

# Kontrolle: jede definierte Fläche steht in der Zeichenreihenfolge
defined = set()
cur = None
for line in out:
    if line == '[_polygon]':
        cur = 'p'
    elif line.startswith('Type=') and cur == 'p':
        defined.add(int(line[5:], 16))
        cur = None
    elif line.startswith('[_'):
        cur = None
ordered = {t for _, ts in DRAW_ORDER for t in ts}
missing = defined - ordered
assert not missing, 'Flächen ohne drawOrder: %s' % [hex(x) for x in missing]

if '--soll-ist' in sys.argv:
    print('# Soll-Ist-Liste Style/TYP gegen SMV25-QGIS\n')
    print('Erzeugt von `src/style/tools/make_typ.py --soll-ist` (nicht von Hand ändern). '
          'Umrechnung %.2f px/mm, siehe docs/stil/stil.md. Soll = Werte aus `SMV25_CHLV95LN02.qgs`.\n' % K)
    print('| Art | Typ | Objekt | Soll (SMV25-QGIS) | Ist (TYP) | Status / Begründung |')
    print('|---|---|---|---|---|---|')
    for kind, t, name, sw, iw, note in SOLL:
        status = note if note else 'gleich'
        print('| %s | 0x%x | %s | %s | %s | %s |' % (kind, t, name, sw.replace('|', '/'), iw.replace('|', '/'), status))
    print('\n## Hinweise\n')
    print('- Status „gleich“: Ist entspricht dem SMV25-Soll nach Umrechnung und Rundung auf ganze Pixel.')
    print('- Jede Zeile nennt den Grund einer Abweichung. Die Garmin-Grenzen und die bewussten Abweichungen '
          'stehen gesammelt in `docs/stil/stil.md`. Garmin-Grenzen sind zum Beispiel: eine Breite je Typ, keine '
          'Schriftart, Muster 32×32 mit 2 Farben, Label-Platzierung durch das Gerät.')
    print('- Diese Typen haben dieselbe Signatur wie der Grundtyp, nur mit anderem Massstab:')
    print('  - 0x109.. (Grobstufen 12–21)')
    print('  - 0x10a.. (Übersicht 21–23)')
    print('  - 0x10b.. (LK50 21–22)')
    print('  - 0x10c.. und 0x10d.. (Auflösung 24 in Geländebreite)')
    print('- Gemessen wird der Fortschritt von style-qa gegen SMR25-Ausschnitte (Berichte dort).')
    print('\n## Zeichenreihenfolge der Flächen\n')
    print('Stufe 1 liegt unten.\n')
    for lvl, ts in DRAW_ORDER:
        print('- %d: %s' % (lvl, ', '.join('0x%x' % t for t in ts)))
else:
    print('\n'.join(head + out))
