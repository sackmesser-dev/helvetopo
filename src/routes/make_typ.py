#!/usr/bin/env python3
"""Erzeugt src/style/typ/routes.txt (TYP-Quelltext für das Routen-Overlay, FID 7702).

Farben und Muster stehen hier zentral; routes.txt nicht von Hand ändern, sondern
dieses Skript anpassen und neu laufen lassen:
    python3 -I src/routes/make_typ.py > src/style/typ/routes.txt

Routenfarben nach den Legenden der Bundes-Geodienste (api3.geo.admin.ch, Layer ch.astra.*),
Stand 2026-11-03: Wanderland #00A800, Veloland #0099FF, Mountainbikeland #CC6600, Skatingland #9900CC.
Veloland ab 2026-11-04 Marineblau #1F3F99 statt #0099FF: Das Originalblau sah in BaseCamp wie
Fluss/Bach aus (Basis-TYP Gewässer #0088D0, Rand #0D4869).
Kanuland hat keinen Bundes-Layer; Türkis ist eine Annahme.
Wanderland ab 2026-11-06 dunkelgrün #007A2E statt #00A800 (Benutzer: muss sich vom Wald abheben).
Wanderwege (Etappe 3) LK-artig rot bzw. blau (Bergwanderweg/Alpinwanderweg-Farben des geo.admin-Layers).
"""

FID = 7702

# Wanderwege (Etappe 3): LK-artige Signatur ÜBER dem Weg der Basiskarte statt breiter Farblinie,
# angelehnt an die Landeskarte mit Wanderwegnetz bzw. die swisstopo-Wanderkarte.
#   Wanderweg: gelb-weiss gestrichelt wie Berg- und Alpinwanderweg (Benutzer, vorher Punktlinie mit
#   transparenten Lücken).
#   Bergwanderweg: rot-weiss gestrichelt (Signalisation weiss-rot-weiss).
#   Alpinwanderweg: blau-weiss gestrichelt (Signalisation weiss-blau-weiss).
#   Review 3: 3 px statt 2 px, wie in der swisstopo-App (im Gebirge sonst kaum sichtbar).
#   Wanderweg #F2A900 statt #D9A400 (Benutzer: satter). Setzt sich vom LK-Gelb der Verbindungsstrasse
#   #FFF582 stärker ab (ΔE 41 statt 36), Kontrast auf Weiss 2,0.
#   Typ, Name DE, Name EN, Farbe, zweite Farbe ("none" = transparent), Breite, Strich (on, off)
TRAILS = [
    (0x10E00, "Wanderweg", "Hiking trail", "#F2A900", "#FFFFFF", 3, (4, 4)),
    (0x10E01, "Bergwanderweg", "Mountain hiking trail", "#C83C32", "#FFFFFF", 3, (4, 4)),
    (0x10E02, "Alpinwanderweg", "Alpine hiking trail", "#2E6FC0", "#FFFFFF", 3, (4, 4)),
]

# SchweizMobil-Routen nah (ab Auflösung 23 ≈ 1:25 000), Etappe 4: Begleitlinie mittig auf dem Weg
# (3 px, Wunsch des Benutzers, vorher 2 px) in leicht aufgehellter Originalfarbe statt Doppelband,
# damit das LK-Bild dominant bleibt (BaseCamp-Test 10: Bänder machten in der Stadt viel Unruhe).
# Das Strichmuster unterscheidet die Länder auch dort, wo zwei Routen denselben Weg nutzen.
#   Typ, Name DE, Name EN, Farbe, Breite, Strichmuster (on, off) oder None
ROUTES = [
    (0x10E10, "Wanderland-Route", "Wanderland route", "#007A2E", 3, None),
    (0x10E11, "Hindernisfreier Weg", "Barrier-free route", "#007A2E", 3, (6, 2)),
    (0x10E12, "Veloland-Route", "Veloland route", "#1F3F99", 3, None),
    (0x10E13, "Mountainbikeland-Route", "Mountainbikeland route", "#CC6600", 3, (12, 4)),
    (0x10E14, "Skatingland-Route", "Skatingland route", "#9900CC", 3, (4, 4)),
    (0x10E15, "Kanuland-Route", "Kanuland route", "#00A3A6", 3, None),
]
LIGHTEN_FINE = 0.2  # Anteil Weiss nah (grob: LIGHTEN)
# Abweichende Aufhellung (nah, grob) je Typ: Velo/MTB/Skating kaum aufhellen, sonst wird Velo
# hellblau wie Gewässer, MTB hellbraun wie Höhenkurven (#D7963C) und Skating rosa wie Grenzen (#ECA8C8).
# Wanderland dunkelgrün #007A2E statt Bundesgrün #00A800 (Benutzer: muss sich vom Wald #CDE6BE abheben,
# Kontrast 4,1 statt 1,9), deshalb ebenfalls kaum aufgehellt.
LIGHTEN_BY_TYPE = {
    0x10E10: (0.0, 0.15),
    0x10E11: (0.0, 0.15),
    0x10E12: (0.0, 0.15),
    0x10E13: (0.0, 0.15),
    0x10E14: (0.0, 0.15),
}

# Grobe Stufen (Auflösung 20–22): nur nationale/regionale Routen, gleich breit wie nah (3 px)
# in aufgehellter Farbe, damit sie wie halbtransparent wirken und die Karte nicht dominieren.
LIGHTEN = 0.45  # Anteil Weiss
ROUTES_COARSE = [  # Typ, Typ nah (für Name/Farbe/Muster), Breite
    (0x10E18, 0x10E10, 3),
    (0x10E1A, 0x10E12, 3),
    (0x10E1B, 0x10E13, 3),
    (0x10E1C, 0x10E14, 3),
    (0x10E1D, 0x10E15, 3),
]


def lighten(color: str, share: float = LIGHTEN) -> str:
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(c + (255 - c) * share):02X}" for c in rgb)


def dash_row(char: str, on: int, off: int, gap: str = " ") -> str:
    # on + off sollte 32 teilen, sonst entsteht an der Bitmap-Naht ein unregelmässiger Strich
    pat = (char * on + gap * off) * (32 // (on + off) + 1)
    return pat[:32]


def line_xpm(color: str, width: int, dash) -> list[str]:
    row = "a" * 32 if dash is None else dash_row("a", *dash)
    out = [f'Xpm="32 {width} 2 1"', f'"a c {color}"', '"  c none"']
    out += [f'"{row}"' for _ in range(width)]
    return out


def trail_xpm(color: str, second: str, width: int, dash) -> list[str]:
    if dash is None:
        # Linie mit Rand: Breite = Linie, Rand je 1 px
        return [f"LineWidth={width}", "BorderWidth=1", 'Xpm="0 0 2 0"',
                f'"a c {color}"', f'"b c {second}"']
    gap = " " if second == "none" else "b"
    row = dash_row("a", dash[0], dash[1], gap=gap)
    out = [f'Xpm="32 {width} 2 1"', f'"a c {color}"', f'"{gap} c {second}"']
    out += [f'"{row}"' for _ in range(width)]
    return out


# Sprachcodes Garmin-TYP: 0x02 Deutsch, 0x01 Französisch, 0x05 Italienisch, 0x04 Englisch.
# Deutsch zuerst (Standard). Begriffe FR/IT eigene Übersetzung; Land-Namen sind Eigennamen.
I18N = {  # DE -> (FR, IT)
    "Wanderweg": ("Chemin de randonnée", "Sentiero escursionistico"),
    "Bergwanderweg": ("Chemin de randonnée de montagne", "Sentiero escursionistico di montagna"),
    "Alpinwanderweg": ("Chemin de randonnée alpine", "Sentiero escursionistico alpino"),
    "Wanderland-Route": ("Route La Suisse à pied", "Percorso La Svizzera a piedi"),
    "Hindernisfreier Weg": ("Chemin sans obstacles", "Percorso senza ostacoli"),
    "Veloland-Route": ("Route La Suisse à vélo", "Percorso La Svizzera in bici"),
    "Mountainbikeland-Route": ("Route La Suisse à VTT", "Percorso La Svizzera in MTB"),
    "Skatingland-Route": ("Route La Suisse en rollers", "Percorso La Svizzera sui pattini"),
    "Kanuland-Route": ("Route La Suisse en canoë", "Percorso La Svizzera in canoa"),
}
# ÖV-Haltestellen (Punkte, src/style/routes/points): blauer Punkt mit weissem Rand,
# Name rot wie die Bahnhöfe der Basiskarte (Basis-TYP 0x2f08, #DD1919).
# Bahnhöfe ohne sichtbares Label (NoLabel): Den Namen zeigt die Basiskarte, der Punkt bleibt suchbar.
#   Typ, Name DE, Name EN
STOPS = [
    (0x10E04, "Bahnhof, Haltestelle Bahn", "Railway station"),
    (0x10E00, "Bushaltestelle", "Bus stop"),
    (0x10E01, "Tramhaltestelle", "Tram stop"),
    (0x10E02, "Schiffstation", "Boat station"),
    (0x10E03, "Seilbahn- oder Bergbahnstation", "Cable car or mountain railway station"),
]
STOPS_NOLABEL = {0x10E04}
STOP_DOT = "#1F66CC"
STOP_LABEL_DAY = "#DD1919"
STOP_LABEL_NIGHT = "#FF6A6A"
I18N.update({
    "Bahnhof, Haltestelle Bahn": ("Gare, halte", "Stazione, fermata"),
    "Bushaltestelle": ("Arrêt de bus", "Fermata del bus"),
    "Tramhaltestelle": ("Arrêt de tram", "Fermata del tram"),
    "Schiffstation": ("Débarcadère", "Approdo"),
    "Seilbahn- oder Bergbahnstation": ("Station de téléphérique ou de chemin de fer de montagne",
                                       "Stazione di funivia o ferrovia di montagna"),
})


SYMBOL_SIZE = 13  # Punktsymbole 13 × 13 px: auf dem GPSMAP 67 waren 7 px kaum sichtbar
RING_PX = 2  # weisser Rand


def symbol_xpm(fill: str, ring: str, glyph=None, glyph_color="#FFFFFF", square=False) -> list[str]:
    """Punkt (Kreis oder Quadrat) mit Rand, optional mit Zeichen in der Mitte
    (Liste gleich langer Zeilen, 'x' = gesetzt)."""
    n, r = SYMBOL_SIZE, SYMBOL_SIZE / 2
    rows = []
    for y in range(n):
        row = ""
        for x in range(n):
            if square:
                d = max(abs(x + 0.5 - r), abs(y + 0.5 - r))
                row += "b" if d <= r - RING_PX else "w"
                continue
            d = ((x + 0.5 - r) ** 2 + (y + 0.5 - r) ** 2) ** 0.5
            row += "b" if d <= r - RING_PX else "w" if d <= r else "."
        rows.append(row)
    colors = [f'"b c {fill}"', f'"w c {ring}"', '". c none"']
    if glyph:
        gy, gx = (n - len(glyph)) // 2, (n - len(glyph[0])) // 2
        for j, line in enumerate(glyph):
            rows[gy + j] = "".join("g" if line[i - gx:i - gx + 1] == "x" and 0 <= i - gx < len(line) else c
                                   for i, c in enumerate(rows[gy + j]))
        colors.insert(2, f'"g c {glyph_color}"')
    return [f'"{n} {n} {len(colors)} 1"'] + colors + [f'"{row}"' for row in rows]


# POIs, die die Landeskarte nicht zeigt (Liste mit dem Basis-Stil abgestimmt). Regeln in
# src/style/routes/points, Tags aus src/vector/pois.py. Name schwarz (das Gerät zeichnet Punktnamen
# ohnehin schwarz), ab Auflösung 24, suchbar.
#   Typ, Name DE, Name EN, Füllfarbe, Zeichen, Quadrat
GLYPH_P = ["xxxx.", "xx.xx", "xx.xx", "xxxx.", "xx...", "xx...", "xx..."]
GLYPH_CUTLERY = ["x.x.x", "x.x.x", "xxx.x", ".x.xx", ".x..x", ".x..x", ".x..x"]
GLYPH_TABLE = ["xxxxxxx", "xxxxxxx", ".x...x.", "xxxxxxx", "x.....x"]
GLYPH_H = ["xx.xx", "xx.xx", "xx.xx", "xxxxx", "xx.xx", "xx.xx", "xx.xx"]
GLYPH_WC = ["x...x.xxx", "x...x.x..", "x.x.x.x..", "xx.xx.x..", "x...x.xxx"]
POIS = [
    (0x10E05, "Parkplatz", "Parking", "#1F66CC", GLYPH_P, True),
    (0x10E06, "Restaurant", "Restaurant", "#8B4A1C", GLYPH_CUTLERY, False),
    (0x10E07, "Rastplatz", "Rest area", "#2E7D32", GLYPH_TABLE, False),
    (0x10E08, "Raststätte", "Motorway service area", "#C05A00", GLYPH_CUTLERY, False),
    (0x10E09, "Toilette", "Toilets", "#555555", GLYPH_WC, True),
    (0x10E0A, "Hotel, Gasthaus", "Hotel, guest house", "#8E2A6B", GLYPH_H, True),
]
I18N.update({
    "Parkplatz": ("Parking", "Parcheggio"),
    "Restaurant": ("Restaurant", "Ristorante"),
    "Rastplatz": ("Aire de repos", "Area di sosta"),
    "Raststätte": ("Aire de service", "Area di servizio"),
    "Toilette": ("Toilettes", "Servizi igienici"),
    "Hotel, Gasthaus": ("Hôtel, auberge", "Albergo, locanda"),
})


def dot_xpm(ring: str) -> list[str]:
    return symbol_xpm(STOP_DOT, ring)


OVERVIEW = ("Übersicht", "aperçu", "panoramica", "overview")


def strings(p, de: str, en: str, overview: bool = False) -> None:
    fr, it = I18N[de]
    names = [de, fr, it, en]
    if overview:
        names = [f"{n} ({o})" for n, o in zip(names, OVERVIEW)]
    for i, (code, name) in enumerate(zip((0x02, 0x01, 0x05, 0x04), names), start=1):
        p(f"String{i}=0x{code:02x},{name}")


def main() -> None:
    p = print
    p("; -*- coding: utf-8 -*-")
    p("; TYP Routen-Overlay Helvetopo (FID 7702). Generiert von src/routes/make_typ.py.")
    p("; Farben nach den Legenden der Bundes-Geodienste (geo.admin), siehe docs/vektor/routen.md.")
    p("; Keine Logos, keine Marken-Icons.")
    p("")
    p("[_id]")
    p(f"FID={FID}")
    p("ProductCode=1")
    p("CodePage=1252")
    p("[end]")
    p("")
    # Leere DrawOrder: das Overlay hat keine Flächen.
    p("[_drawOrder]")
    p("[end]")
    p("")
    for typ, de, en, col, second, width, dash in TRAILS:
        p("[_line]")
        p(f"Type=0x{typ:05x}")
        p("UseOrientation=Y")
        for line in trail_xpm(col, second, width, dash):
            p(line)
        strings(p, de, en)
        p("ExtendedLabels=Y")
        p("FontStyle=NoLabel")
        p("[end]")
        p("")
    for typ, de, en, col, width, dash in ROUTES:
        p("[_line]")
        p(f"Type=0x{typ:05x}")
        p("UseOrientation=Y")
        for line in line_xpm(lighten(col, LIGHTEN_BY_TYPE.get(typ, (LIGHTEN_FINE,))[0]), width, dash):
            p(line)
        strings(p, de, en)
        p("ExtendedLabels=Y")
        p("FontStyle=NormalFont")
        p(f"DayCustomColor={col}")
        p(f"NightCustomColor={col}")
        p("[end]")
        p("")
    fine = {r[0]: r for r in ROUTES}
    for typ, ref, width in ROUTES_COARSE:
        _, de, en, col, _, dash = fine[ref]
        p("[_line]")
        p(f"Type=0x{typ:05x}")
        p("UseOrientation=Y")
        for line in line_xpm(lighten(col, LIGHTEN_BY_TYPE.get(ref, (0, LIGHTEN))[1]), width, dash):
            p(line)
        strings(p, de, en, overview=True)
        p("ExtendedLabels=Y")
        p("FontStyle=SmallFont")
        p(f"DayCustomColor={col}")
        p(f"NightCustomColor={col}")
        p("[end]")
        p("")
    for typ, de, en in STOPS:
        p("[_point]")
        p(f"Type=0x{typ:05x}")
        strings(p, de, en)
        p("ExtendedLabels=Y")
        if typ in STOPS_NOLABEL:
            p("FontStyle=NoLabel")
        else:
            p("FontStyle=NormalFont")
            p(f"DayCustomColor={STOP_LABEL_DAY}")
            p(f"NightCustomColor={STOP_LABEL_NIGHT}")
        day, night = dot_xpm("#FFFFFF"), dot_xpm("#202020")
        p("DayXpm=" + day[0])
        for line in day[1:]:
            p(line)
        p("NightXpm=" + night[0])
        for line in night[1:]:
            p(line)
        p("[end]")
        p("")
    for typ, de, en, fill, glyph, square in POIS:
        p("[_point]")
        p(f"Type=0x{typ:05x}")
        strings(p, de, en)
        p("ExtendedLabels=Y")
        p("FontStyle=NormalFont")
        day = symbol_xpm(fill, "#FFFFFF", glyph, square=square)
        night = symbol_xpm(fill, "#202020", glyph, square=square)
        p("DayXpm=" + day[0])
        for line in day[1:]:
            p(line)
        p("NightXpm=" + night[0])
        for line in night[1:]:
            p(line)
        p("[end]")
        p("")


if __name__ == "__main__":
    main()
