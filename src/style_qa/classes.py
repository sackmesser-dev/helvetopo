"""Zuordnung SMV25-Objektart (Layer + Feld „Symbol“) ↔ Garmin-Typ (unser Style).

Jede Klasse: key, Name, Art (line/area), SMV25-Layer, SQL-Filter auf „Symbol“, Garmin-Typen.
Die Zuordnung folgt docs/stil/stil.md. Wo der Style eine SMV-Klasse
zusammenfasst oder aufteilt, steht das in 'hinweis'.
"""

LINES = [
    # key, name, layer, where, garmin types
    ('autobahn', 'Autobahn', 'T45_DKM25_STRASSE', "Symbol LIKE 'Autobahn%'", ['0x1']),
    ('autostrasse', 'Autostrasse/Zufahrt', 'T45_DKM25_STRASSE', "Symbol LIKE 'Autostrasse%'", ['0x2', '0x9']),
    ('durchgang', 'Durchgangsstrasse', 'T45_DKM25_STRASSE', "Symbol LIKE 'Durchgangsstrasse%'", ['0x3']),
    ('verbindung', 'Verbindungsstrasse', 'T45_DKM25_STRASSE', "Symbol LIKE 'Verbindungsstrasse%'", ['0x4']),
    ('str6', 'Strasse 6–10 m', 'T45_DKM25_STRASSE',
     "Symbol LIKE 'Strasse (6m%' OR Symbol LIKE 'Strasse (8m%' OR Symbol LIKE 'Strasse (10m%'", ['0x5']),
    ('str4', 'Strasse 4 m', 'T45_DKM25_STRASSE', "Symbol LIKE 'Strasse (4m%'", ['0x6']),
    ('str3', 'Strasse 3 m (Hart- und Naturbelag)', 'T45_DKM25_STRASSE', "Symbol LIKE 'Strasse (3m%' OR Symbol = 'Strasse (Platz)'", ['0x7', '0xa']),
    ('str2', 'Strasse 2 m', 'T45_DKM25_STRASSE', "Symbol LIKE 'Strasse (2m%'", ['0x8']),
    ('weg2', 'Weg 2 m (Naturbelag, nicht befahrbar)', 'T45_DKM25_STRASSE', "Symbol LIKE 'Weg (2m%'", ['0xe']),
    ('weg1', 'Weg 1 m', 'T45_DKM25_STRASSE', "Symbol LIKE 'Weg (1m%'", ['0x16']),
    ('spur', 'Markierte Spur / Wegfragment', 'T45_DKM25_STRASSE', "Symbol LIKE 'Markierte Spur%'", ['0xf']),
    ('normalspur', 'Normalspur einspurig', 'T44_DKM25_EISENBAHN', "Symbol LIKE 'Normalspur (Einspur%'", ['0x14']),
    ('normalspur2', 'Normalspur mehrspurig', 'T44_DKM25_EISENBAHN', "Symbol LIKE 'Normalspur (Mehrspur%'", ['0x10e00']),
    ('schmalspur', 'Schmalspur', 'T44_DKM25_EISENBAHN', "Symbol LIKE 'Schmalspur%'", ['0x10e01']),
    ('anschluss', 'Anschlussgleis', 'T44_DKM25_EISENBAHN', "Symbol LIKE 'Anschlussgleis%'", ['0x10e02']),
    ('bahntunnel', 'Bahntunnel', 'T46_DKM25_EISENBAHN_TUNNEL', None, ['0x10e07']),
    ('fluss', 'Fliessgewässer ≥ 0,2 mm (Fluss)', 'T57_DKM25_GEWAESSER_LIN',
     "Symbol LIKE 'Fliessgewässer (0.2%' OR Symbol LIKE 'Fliessgewässer (0.3%' OR Symbol LIKE 'Fliessgewässer (0.4%'", ['0x1f']),
    ('bach', 'Fliessgewässer < 0,2 mm (Bach)', 'T57_DKM25_GEWAESSER_LIN',
     "Symbol LIKE 'Fliessgewässer (0.1%'", ['0x18']),
    ('trockenrinne', 'Trockenrinne', 'T57_DKM25_GEWAESSER_LIN', "Symbol = 'Trockenrinne'", ['0x26']),
    ('kurve', 'Höhenkurve (Normalkurve braun)', 'T62_DKM25_HOEHENKURVE', "Symbol = 'Normalkurve (braun)'", ['0x20', '0x21', '0x11005']),
    ('zaehlkurve', 'Höhenkurve (Zählkurve braun)', 'T62_DKM25_HOEHENKURVE', "Symbol = 'Zählkurve (braun)'", ['0x22']),
    ('kurve_fels', 'Höhenkurve Fels (schwarz)', 'T62_DKM25_HOEHENKURVE', "Symbol LIKE '%(schwarz)'", ['0x10f00', '0x10f01', '0x11001', '0x11002', '0x11006']),
    ('kantonsgrenze', 'Kantonsgrenze', 'T53_DKM25_HOHEITSGRENZE', "Symbol = 'Kantonsgrenze'", ['0x1c']),
    ('bezirksgrenze', 'Bezirksgrenze', 'T53_DKM25_HOHEITSGRENZE', "Symbol = 'Bezirksgrenze'", ['0x10f04']),
    ('gemeindegrenze', 'Gemeindegrenze', 'T53_DKM25_HOHEITSGRENZE', "Symbol = 'Gemeindegrenze'", ['0x10f05']),
    ('hochspannung', 'Hochspannungsleitung', 'T40_DKM25_BAUTE_LIN', "Symbol = 'Hochspannungsleitung'", ['0x29']),
    ('mauer', 'Mauer, Laufbahn', 'T40_DKM25_BAUTE_LIN', "Symbol LIKE 'Laufbahn/Mauer%' OR Symbol = 'Trockenmauer'", ['0x10f07']),
    ('verbauung', 'Gewässerverbauung, Hafensteg', 'T40_DKM25_BAUTE_LIN', "Symbol IN ('Gewässerverbauung','Hafensteg')", ['0x10f0e']),
    ('seilbahn', 'Luftseilbahn, Gondel, Sessel', 'T42_DKM25_OEV_LIN', "Symbol IN ('Luftseilbahn','Gondel-/Sesselbahn')", ['0x10e04']),
    ('skilift', 'Skilift', 'T42_DKM25_OEV_LIN', "Symbol = 'Skilift'", ['0x10e05']),
]

# Strassen ab Stil-Etappe 8: Routingtyp 0x01–0x16 nur in Auflösung 24, darunter Übersichtstyp
# 0x10a00|Typ (nicht routingfähig). Beide gehören zur selben LK-Klasse.
ROAD_TYPES = {'0x%x' % t for t in list(range(0x1, 0x17))}
for _i, _c in enumerate(LINES):
    if _c[2] == 'T45_DKM25_STRASSE':
        # Etappe 8: 0x10a00|Typ (Auflösung ≤ 23), Etappe 10: 0x10b00|Typ (Auflösung 21–22)
        LINES[_i] = _c[:4] + (_c[4] + ['0x%x' % (base | int(t, 16)) for base in (0x10a00, 0x10b00)
                                       for t in _c[4] if t in ROAD_TYPES],)

AREAS = [
    ('wald', 'Wald', 'T65_DKM25_BODENBEDECKUNG', "Symbol = 'Wald'", ['0x50']),
    ('see', 'See', 'T56_DKM25_GEWAESSER_PLY', "Symbol LIKE 'See%'", ['0x3c', '0x3e', '0x41', '0x4c']),
    ('flussflaeche', 'Fluss (Fläche)', 'T56_DKM25_GEWAESSER_PLY', "Symbol = 'Fluss'", ['0x48']),
    ('gebaeude', 'Gebäude', 'T48_DKM25_GEBAEUDE', "Symbol IN ('Gebäude','Hochhaus','Sakraler Turm','Kapelle','Turm','Hochkamin','Mauer (gross)')", ['0x13']),
    ('obst', 'Obstanlage', 'T64_DKM25_NUTZUNGSAREAL', "Symbol = 'Obstanlage'", ['0x4e']),
    ('friedhof', 'Friedhof', 'T64_DKM25_NUTZUNGSAREAL', "Symbol = 'Friedhof'", ['0x1a']),
    ('park', 'Parkareal, Schrebergarten', 'T64_DKM25_NUTZUNGSAREAL', "Symbol IN ('Oeffentliches Parkareal','Schrebergartenareal')", ['0x17']),
    ('sport', 'Freizeitanlage, Sport', 'T63_DKM25_FREIZEITAREAL', "Symbol = 'Freizeitanlagenareal'", ['0x19']),
    ('spital', 'Spitalareal', 'T64_DKM25_NUTZUNGSAREAL', "Symbol = 'Spitalareal'", ['0xb']),
    ('parkplatz', 'Parkplatz, Verkehrsfläche', 'T61_DKM25_VERKEHRSAREAL', None, ['0x5', '0x1100a']),
]

# Zeichenreihenfolge: Paare (oben, unten) laut SMV25-Layerfolge; gemessen wird, welche Farbe an
# den Überlagerungspixeln sichtbar ist.
ORDER_PAIRS = [
    ('str4', 'bach'), ('str3', 'bach'), ('verbindung', 'fluss'), ('str4', 'kurve'),
    ('weg2', 'kurve'), ('normalspur', 'str4'), ('gebaeude', 'wald'), ('str4', 'gemeindegrenze'),
    ('hochspannung', 'str4'), ('bach', 'kurve'), ('str3', 'wald'), ('weg1', 'wald'),
]

# Beschriftungen: SMV25-Annotationslayer ↔ Garmin-Typen, die diese Namen tragen.
LABELS = [
    ('siedlung', 'Siedlungsnamen', ['T11_DKM25_SIEDLUNGSNAME_ANNO'],
     ['0x100', '0x200', '0x300', '0x400', '0x500', '0x600', '0x700', '0x800', '0x900', '0xa00', '0xb00',
      '0xc00', '0xd00', '0xe00', '0xf00', '0x1000', '0x1100', '0x1150d', '0x1150e']),
    ('flur', 'Flur- und Lokalnamen', ['T14_DKM25_FLURNAME_ANNO'], ['0x2800']),
    ('gelaende', 'Gelände-, Gebiets- und Bergnamen', ['T12_DKM25_GELAENDENAME_ANNO', 'T13_DKM25_GEBIETSNAME_ANNO', 'T01_DKM25_NAME_PKT_ANNO'],
     ['0x6616', '0x6602', '0x6617', '0x6611', '0x6613', '0x660b', '0x6614']),
    ('gewaesser', 'Gewässernamen', ['T15_DKM25_GEWAESSER_LIN_ANNO', 'T16_DKM25_GEWAESSER_PLY_ANNO'],
     ['0x1f', '0x18', '0x650d', '0x650a', '0x3c', '0x3e', '0x41', '0x48']),
    ('strasse', 'Strassennamen', ['T03_DKM25_STRASSE_ANNO', 'T02_DKM25_STRASSE_PKT_ANNO'],
     ['0x1', '0x2', '0x3', '0x4', '0x5', '0x6', '0x7', '0x8', '0x9', '0xa', '0xe', '0x16']),
    ('gebaeude', 'Gebäude- und Objektnamen', ['T07_DKM25_GEBAEUDE_ANNO', 'T08_DKM25_BAUTE_PKT_ANNO', 'T10_DKM25_BAUTE_PLY_ANNO',
                                             'T25_DKM25_FREIZEITAREAL_ANNO', 'T26_DKM25_NUTZUNGSAREAL_ANNO'],
     ['0x6402', '0x6404', '0x2c0b', '0x2c02', '0x2c04', '0x6411', '0x2f08', '0x3002', '0x13', '0xb', '0x19', '0x1a']),
    ('kote', 'Höhenkoten', ['T17_DKM25_HOEHENKOTE_ANNO'], ['0x6300', '0x6616', '0x660b', '0x1150f', '0x11510']),
    ('kurve', 'Höhenkurvenzahlen', ['T18_DKM25_HOEHENKURVE_ANNO'], ['0x20', '0x21', '0x22']),
]

# Punktsymbole: SMV25-Punktlayer/Symbol ↔ Garmin-Punkttypen
SYMBOLS = [
    ('kirche', 'Kirche, sakraler Turm', 'T48_DKM25_GEBAEUDE', "Symbol = 'Sakraler Turm'", ['0x6404']),
    ('kapelle', 'Kapelle', 'T48_DKM25_GEBAEUDE', "Symbol = 'Kapelle'", ['0x2c0b']),
    ('hoehenkote', 'Höhenkote', 'T38_DKM25_HOEHENKOTE', None, ['0x6300', '0x6616', '0x660b', '0x1150f', '0x11510']),
    ('einzelbaum', 'Einzelbaum', 'T36_DKM25_EINZELBAUM', None, ['0x6618', '0x11509', '0x1150a', '0x1150c']),
    ('bahnhof', 'Bahnhof, Haltestelle', 'T30_DKM25_OEV_PKT', None, ['0x2f08', '0x2f17']),
    ('baute_pkt', 'Einzelobjekte (Brunnen, Antenne, Kreuz …)', 'T32_DKM25_BAUTE_PKT', None,
     ['0x5000', '0x6511', '0x11501', '0x11502', '0x11503', '0x11504', '0x11505', '0x11506', '0x11507', '0x11508', '0x6411', '0x2c04']),
    ('gipfel', 'Gipfel, Pass (Namenpunkte)', 'T37_DKM25_NAME_PKT', None, ['0x6616', '0x660b']),
    ('morph', 'Kleinformen (Doline, Felsblock, Höhle)', 'T39_DKM25_MORPH_KLEINFORM_PKT', None, ['0x6601', '0x6614']),
    ('feuchtgebiet', 'Feuchtgebiet (Signatur)', 'T43_DKM25_BODENBEDECKUNG_SYMB', "Symbol = 'Feuchtgebiet'", ['0x51']),
]
