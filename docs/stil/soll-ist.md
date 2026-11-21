# Soll-Ist-Liste Style/TYP gegen SMV25-QGIS

Erzeugt von `src/style/tools/make_typ.py --soll-ist` (nicht von Hand ändern). Umrechnung 10.40 px/mm, siehe docs/stil/stil.md. Soll = Werte aus `SMV25_CHLV95LN02.qgs`.

| Art | Typ | Objekt | Soll (SMV25-QGIS) | Ist (TYP) | Status / Begründung |
|---|---|---|---|---|---|
| Linie | 0x1 | Autobahn | Autobahn (round) 0,68/0,36: #FBBF39 innen 0,36 mm, Rand #000000 0,16 mm | 5 + 2×2 px | SMV zeichnet je Fahrbahn eine Linie. TLM liefert ebenfalls getrennte Fahrbahnen. |
| Linie | 0x2 | Autostrasse | Autostrasse/Zufahrt (6m, round) 0,70/0,46: #FBBF39 innen 0,46 mm, Rand #000000 0,12 mm | 5 + 2×2 px | gleich |
| Linie | 0x9 | Ein-/Ausfahrt | Autostrasse Einfahrt/Raststaette (4m) 0,62/0,38: #FBBF39 innen 0,38 mm, Rand #000000 0,12 mm | 4 + 2×2 px | gleich |
| Linie | 0x3 | Durchgangsstrasse | Durchgangsstrasse (8m, round) 0,78/0,54: #F5AE95 innen 0,54 mm, Rand #000000 0,12 mm | 6 + 2×2 px | eine Breite für alle Breitenklassen (Routingtyp je Farbe), häufigste Klasse 8 m. SMV 3m–10m: 0,30–0,62 mm innen. |
| Linie | 0x4 | Verbindungsstrasse | Verbindungsstrasse (6m, round) 0,70/0,46: #FFF582 innen 0,46 mm, Rand #000000 0,12 mm | 5 + 2×2 px | wie Durchgangsstrasse |
| Linie | 0x5 | Strasse 6 m und breiter | Strasse (6m, round) 0,70/0,46: #FFFFFF innen 0,46 mm, Rand #000000 0,12 mm | 5 + 2×2 px | 10 m (0,62) und 8 m (0,54) zusammengefasst, Typ-Mangel |
| Linie | 0x6 | Strasse 4 m | Strasse (4m, round) 0,62/0,38: #FFFFFF innen 0,38 mm, Rand #000000 0,12 mm | 4 + 2×2 px | gleich |
| Linie | 0x7 | Strasse 3 m | Strasse (3m, round) 0,54/0,30: #FFFFFF innen 0,30 mm, Rand #000000 0,12 mm | 3 + 2×2 px | gleich |
| Linie | 0x8 | Strasse 2 m, Hartbelag | Strasse (2m, round) 0,46/0,22: #FFFFFF innen 0,22 mm, Rand #000000 0,12 mm | 2 + 2×2 px | gleich |
| Linie | 0xa | Fahrweg, Naturbelag | Strasse (3m, Naturbelag): #FFFFFF 0,54 mm, Randpunkte #000000 0,265 mm | 7 px, Randzeilen xxx...xx | Punkte als Strichmuster der Randzeilen |
| Linie | 0xe | Weg 2 m | Weg (2m, Naturbelag): #000000 0,18 mm | 2 px | gleich |
| Linie | 0x10 | Weg 2 m, nicht befahrbar | Weg (2m, nicht befahrbar): #000000 0,18 mm, Strich 3,00/0,30 mm | 2 px, xxxxxxxxxxxxxxxxxxxxxxxxxxxxx... | gleich |
| Linie | 0x16 | Weg 1 m | Weg (1m): #000000 0,18 mm, Strich 1,20/0,30 mm | 2 px, xxxxxxxxxxxxx...xxxxxxxxxxxxx... | gleich |
| Linie | 0xf | Wegspur | Markierte Spur: Punkte #000000 0,265 mm | 3 px, xxx........xxx.......xxxx....... | Abstand der Punkte geschätzt (MarkerLine-Intervall nicht ausgelesen) |
| Linie | 0x11 | Treppe | Strasse (Treppe): Querstriche #000000 | 4 px Querstriche | gleich |
| Linie | 0x12 | Klettersteig | – (SMV ohne eigene Signatur) | 3 px, Linie mit Querstrichen | eigene Signatur |
| Linie | 0x13 | Strassentunnel | Strasse (Tunnel): gestrichelte Ränder #000000, Strich 0,79/0,49 mm | 7 px, Ränder xxxxxxxxxx......xxxxxxxxxx...... | ein Tunneltyp für alle Klassen (Routingtypen knapp) |
| Linie | 0x10a00 | Strassen-Übersichtstypen 0x10a01–0x10a16 | wie die Routingtypen, mm × 6.25 px/mm (Gerät 180 dpi) | Auflösung ≤ 23, nicht routingfähig, nur Routennummer als Label | TYP hat nur eine Breite je Typ. Darum hat jede Zoomstufe einen eigenen Typ (Routing läuft auf Auflösung 24). |
| Linie | 0x10900 | Strassen-Grobstufe 0x10901–0x10904 | LK100/LK200: Autobahn, Autostrasse, Durchgangs- und Verbindungsstrasse | wie Übersichtstypen, Auflösung 12–20 (Autobahn), 14–20, 16–20, 18–20 | nur Autobahn/Autostrasse mit Nummer, Tunnel durchgezogen |
| Linie | 0x10907 | Strasse 6 m, Übersicht | LK200: Nebenstrasse weiss mit schwarzem Rand | 1 + 2×1 px | Auflösung 19–20 (Review 2) |
| Linie | 0x10b06 | Strasse 4 m, Stufe LK50 | LK50: Nebenstrasse als feine Doppellinie | 1 + 2×1 px | Auflösung 21–22, generalisiert |
| Linie | 0x10b07 | Strasse 3 m / 2 m, Stufe LK50 | LK50: schmale Strassen als feine Linie | 1 px #000000 | Auflösung 22, generalisiert (Linie statt Doppellinie) |
| Linie | 0x10b16 | Fahrwege und Wege, Stufe LK50 | LK50: Wege schwarz gestrichelt | 1 px #000000, xxxxxxx....xxxxxxx...xxxxxxx.... | Auflösung 22, generalisiert |
| Linie | 0x1a | Autofähre | Autofähre: #000000 0,14 mm, Strich 0,99/0,40 mm | 1 px, xxxxxxxxxxx.....xxxxxxxxxxx..... | gleich |
| Linie | 0x1b | Personenfähre | Personenfähre (ohne Seil): #000000 0,12 mm, Strich 2,49/0,99 mm | 1 px, xxxxxxxxxxxxxxxxxxxxxxx......... | gleich |
| Linie | 0x27 | Piste (Linie) | Hartbelagpiste ist Fläche (T60), Rand #262626 0,12 mm | 3 + 2×1 px | Rückfall für Pisten ohne Fläche |
| Linie | 0x14 | Normalspur | Normalspur (Einspur): #DD1919 0,32 mm | 2 px | Breite × 0,7 (Review 1) |
| Linie | 0x10e00 | Normalspur mehrspurig | Normalspur (Mehrspur): #DD1919 0,76 mm, Mitte #FFFFFF 0,22 mm | 3 px (1 rot, 1 weiss, 1 rot) | Breite × 0,7 (Review 1) |
| Linie | 0x10e01 | Schmalspur | Schmalspur (Einspur): #DD1919 0,22 mm | 1 px | Breite × 0,7 (Review 1) |
| Linie | 0x10e02 | Anschlussgleis | Anschlussgleis: #DD1919 0,10 mm | 1 px | gleich breit wie Schmalspur (Mindestbreite 1 px) |
| Linie | 0x10e03 | Tram, Gleise auf Strasse | Gleise auf Strasse: #DD1919 0,10 mm | 1 px | gleich |
| Linie | 0x10e07 | Bahntunnel | Eisenbahn Tunnel: #DD1919 gestrichelt | 2 px, xxxxx...xxxxx...xxxxx...xxxxx... | Strichlänge geschätzt |
| Linie | 0x10e04 | Luftseilbahn | Luftseilbahn: #DD1919 0,20 mm + Stützensymbole | 1 px + Querstriche alle 16 px | gleich |
| Linie | 0x10e05 | Skilift | Skilift: #D7963C 0,15 mm + Symbole | 1 px + Querstriche | gleich |
| Linie | 0x10e08 | Transportseil, Förderband | Transportseil: #000000 0,18 mm, Symbole #333333 | 1 px + Querstriche | gleich |
| Linie | 0x1f | Fluss | Fliessgewässer (0,12–0,40): #0088D0 | 2 px (0,30 mm) | SMV-Breite je Gewässer variabel, hier zwei Stufen |
| Linie | 0x18 | Bach | Fliessgewässer (0,14): #0088D0 | 1 px | gleich |
| Linie | 0x26 | Trockenrinne | Trockenrinne: Punkte #000000 0,265 mm | 1 px, xx..xx..xx..xx..xx..xx..xx..xx.. | gleich |
| Linie | 0x10e10 | Druckleitung | Druckleitung: #0088D0 0,22 mm + Symbol | 1 px | ohne Symbole |
| Linie | 0x10e11 | Wasserfall | Wasserfall: #0088D0 + Symbol #F2F2F2/#0088D0 | 3 px Zickzack | eigenes Muster |
| Linie | 0x1e | Landesgrenze | Landesgrenze: Band #ECA8C8 2,0 mm, Linie #C22976 0,16 mm | 11 px Band, 1 px Linie | auf ungerade Zeilenzahl aufgerundet (Linie mittig) |
| Linie | 0x1c | Kantonsgrenze | Kantonsgrenze: Band #ECA8C8 1,0 mm, Linie #C22976 0,16 mm | 5 px Band, 1 px Linie | gleich |
| Linie | 0x10f04 | Bezirksgrenze | Bezirksgrenze: #ECA8C8 0,40 mm | 3 px | gleich |
| Linie | 0x10f05 | Gemeindegrenze | Gemeindegrenze: #ECA8C8 0,40 mm, Strich 3,0/0,6 mm | 3 px, xxxxxxxxxxxxxxxxxxxxxxxxxxx..... | gleich |
| Linie | 0x10f06 | Nationalpark | Nationalpark: #A0CF83 0,16 mm + Band | 2 px | ohne Band |
| Linie | 0x29 | Hochspannungsleitung | Hochspannungsleitung: #0088D0 0,14 mm, Strich-Punkt 2,47/0,40/0,20/0,40 mm | 1 px, xxxxxxxxxxxxxxxxxxxxxxx....x.... | gleich |
| Linie | 0x10f0e | Gewässerverbauung, Hafensteg | Gewässerverbauung/Hafensteg: #0088D0 0,14/0,18 mm | 1 px | gleich |
| Linie | 0x10c00 | Bahn, Gewässer, Grenzen in Auflösung 24 (0x10c.., 0x10d.., 0x111..) | wie Auflösung 23, mm × 12.5 px/mm (LK-Geländebreite) | eigene Typen nur für Auflösung 24 | TYP hat nur eine Breite je Typ. Zuordnung: D24 in make_typ.py. |
| Linie | 0x20 | Höhenkurve 10 m | Normalkurve (braun): #D7963C 0,10 mm | 1 px, aufgehellt | nahe Stufen dezent (Review 2) |
| Linie | 0x21 | Höhenkurve | Normalkurve (braun): #D7963C 0,10 mm | 1 px, aufgehellt | nahe Stufen dezent (Review 2) |
| Linie | 0x22 | Zählkurve | Zählkurve (braun): #D7963C 0,18 mm | 2 px | einzige kräftige Kurve in 23/24 (Review 2) |
| Linie | 0x10f15 | Zählkurve (grob) | Zählkurve (braun): #D7963C 0,18 mm | 1 px | Auflösung 21, nur 100-m-Kurven (Review 2) |
| Linie | 0x10f12 | Höhenkurve Fels 10 m | Normalkurve (schwarz): #3E3E3E 0,08 mm | 1 px, aufgehellt | nahe Stufen dezent (Review 2) |
| Linie | 0x10f00 | Höhenkurve Fels | Normalkurve (schwarz): #3E3E3E 0,08 mm | 1 px, aufgehellt | nahe Stufen dezent (Review 2) |
| Linie | 0x10f01 | Zählkurve Fels | Zählkurve (schwarz): #3E3E3E 0,16 mm | 2 px | einzige kräftige Kurve in 23/24 (Review 2) |
| Linie | 0x10f17 | Zählkurve Fels (grob) | Zählkurve (schwarz): #3E3E3E 0,16 mm | 1 px | Auflösung 21, nur 100-m-Kurven (Review 2) |
| Linie | 0x10f13 | Höhenkurve Gletscher/See 10 m | Normalkurve (blau): #0088D0 0,10 mm | 1 px, aufgehellt | nahe Stufen dezent (Review 2) |
| Linie | 0x10f02 | Höhenkurve Gletscher/See | Normalkurve (blau): #0088D0 0,10 mm | 1 px, aufgehellt | nahe Stufen dezent (Review 2) |
| Linie | 0x10f03 | Zählkurve Gletscher/See | Zählkurve (blau): #0088D0 0,18 mm | 2 px | einzige kräftige Kurve in 23/24 (Review 2) |
| Linie | 0x10f19 | Zählkurve Gletscher/See (grob) | Zählkurve (blau): #0088D0 0,18 mm | 1 px | Auflösung 21, nur 100-m-Kurven (Review 2) |
| Linie | 0x10f10 | Landesgrenze Übersicht | wie Landesgrenze | 5 px Band | Auflösung 16–21: Band verschmälert (LK200/500 generalisiert ebenfalls) |
| Linie | 0x10f11 | Kantonsgrenze Übersicht | wie Kantonsgrenze | 3 px Band | Auflösung 20–21, wie oben |
| Linie | 0x10f07 | Mauer | Laufbahn/Mauer: #000000 0,14–0,20 mm | 1 px | gleich |
| Linie | 0x10f08 | Böschung | Böschung: Fläche #D7963C (T51) | 3 px Kamm | als Linie mit Kamm, Daten nur als Linie |
| Linie | 0x10f09 | Felswand | Fels (Raster) #3F3F3F | 4 px Kamm | eigene Signatur, keine Felszeichnung möglich |
| Linie | 0x10f1a | Felsschraffe (Lichtseite) | FELS (Raster): #3F3F3F | Kamm 7 px #7A7A7A | aus DEM erzeugt, Lichtseite heller (Review 3) |
| Linie | 0x10f1b | Felsschraffe (Schattenseite) | FELS (Raster): #3F3F3F | Kamm 7 px | aus DEM erzeugt (Review 3) |
| Linie | 0x10f0b | Staumauer (Linie) | Staumauer: #CCCCCC, Rand #262626 0,12 mm | 3 + 2×1 px | gleich |
| Linie | 0x10f0c | Arealrand grün | Areale T63/T64: Rand #70B446 0,12 mm | 1 px | Garmin-Flächen haben keinen Rand: eigene Linie |
| Linie | 0x10f0d | Arealrand dunkel | Areale T60/T61/T64: Rand #262626 0,12 mm | 1 px | wie oben |
| Fläche | 0x3c | See gross | See (gross): #D2EEFF, Rand #0088D0 0,16 mm | #D2EEFF | ohne Uferlinie (Garmin-Flächen ohne Rand) |
| Fläche | 0x3d | See gross (Übersicht) | wie 0x3c | #D2EEFF | Auflösung 12–20 ohne Namen (Teilflächen) |
| Fläche | 0x3f | See (Übersicht) | wie 0x3e | #D2EEFF | Auflösung 18–20 ohne Namen (Teilflächen) |
| Fläche | 0x3e | See | See: #D2EEFF, Rand #0088D0 0,14–0,16 mm | #D2EEFF | wie oben |
| Fläche | 0x41 | Kleiner See, Weiher | See (klein), Wasserbecken: #D2EEFF, Rand #0088D0 0,12–0,14 mm | #D2EEFF | wie oben |
| Fläche | 0x48 | Fluss (Fläche) | Fluss: #9CD5F8, Rand #0088D0 0,12 mm | #9CD5F8 | wie oben |
| Fläche | 0x4c | See mit wechselndem Wasserstand | See (wechselnder Wasserstand): #D2EEFF, Rand #0088D0 0,18 mm | Muster 32×32 #0088D0 auf #D2EEFF | eigene Kennzeichnung durch Linien |
| Fläche | 0x11004 | Schwimmbecken | Schwimmbecken: #0088D0 | #0088D0 | gleich |
| Fläche | 0x50 | Wald | Wald: #CDE6BE | #CDE6BE | gleich |
| Fläche | 0x11000 | Wald offen | offener Wald: Symbole #70B446 0,38–0,44 mm | Muster 32×32 #70B446 auf transparent | Symbolpunkte aus den Daten → regelmässiges Muster (Abstand geschätzt 1,0 mm) |
| Fläche | 0x4f | Gebüschwald | Gebüschwald: Symbole #70B446 0,25–0,42 mm | Muster 32×32 #70B446 auf transparent | wie offener Wald (Abstand geschätzt 0,7 mm) |
| Fläche | 0x51 | Feuchtgebiet | Feuchtgebiet: Symbol #0088D0 1,0 mm (waagrechte Striche) | Muster 32×32 #0088D0 auf transparent | Symbol als 5-px-Strich im versetzten Raster |
| Fläche | 0x11001 | Fels | FELS (Raster): #3F3F3F auf transparent | Muster 32×32 #3F3F3F auf transparent | Felszeichnung nach Gelände nur über die DEM-Schraffen: gestreute Striche, 10 % Deckung (Review 3) |
| Fläche | 0x11002 | Geröll | GEROELL (Raster): #3F3F3F Punkte auf transparent | Muster 32×32 #3F3F3F auf transparent | gestreute Punkte, 6 % Deckung (Review 3) |
| Fläche | 0x11010 | Schatten | Schummerung (Raster, kräftig im Gebirge) | Muster 32×32 #50647D auf transparent | zusätzlich zur Garmin-Schummerung: Raster 12,5 % #50647D (Review 3) |
| Fläche | 0x11011 | Schatten stark | Schummerung (Raster, kräftig im Gebirge) | Muster 32×32 #50647D auf transparent | wie 0x11010, zusätzlich 12,5 % (zusammen 25 %) |
| Fläche | 0x4d | Gletscher | GLETSCHER (Raster): #006BC7 Linien auf transparent | Muster 32×32 #006BC7 auf transparent | Linien nach Gelände nicht möglich: kurze Striche |
| Fläche | 0x11006 | Reben | Reben: Symbol #70B446 im Raster 0,6 × 1,8 mm | Muster 32×32 #70B446 auf transparent | Rebsymbol als 4-px-Senkrechtstrich |
| Fläche | 0x4e | Obstanlage | Obstanlage: Kreis #70B446 0,24 mm im Raster 0,8 mm | Muster 32×32 #70B446 auf transparent | Kreis als 3-px-Kreuz |
| Fläche | 0x11007 | Baumschule | Baumschule: Kreis #70B446 0,20 mm im Raster 0,7 mm | Muster 32×32 #70B446 auf transparent | gleich |
| Fläche | 0x1a | Friedhof | Friedhof: #E7F3E1, Rand #70B446 0,12 mm | #E7F3E1 | Rand als Linie 0x10f0c |
| Fläche | 0x17 | Park, Schrebergarten | Öffentliches Parkareal, Schrebergarten: #E7F3E1, Rand #70B446 | #E7F3E1 | Rand als Linie |
| Fläche | 0x11005 | Deponie, Abbau | Deponieareal: #F0DABC | #F0DABC | gleich |
| Fläche | 0xb | Spitalareal | Spitalareal: #F2F2F2 | #F2F2F2 | gleich |
| Fläche | 0xc | Unterwerk, Kraftwerk | Unterwerkareal: #FFFFFF, Rand #262626 | #FFFFFF | Rand als Linie 0x10f0d |
| Fläche | 0x11003 | Campingplatz | Campingplatzareal: #E7F3E1, Rand #70B446 | #E7F3E1 | Rand als Linie |
| Fläche | 0x18 | Golfplatz | Golfplatzareal: #E7F3E1, Rand #70B446 | #E7F3E1 | Rand als Linie |
| Fläche | 0x5 | Parkplatz | Parkplatzareal: #FFFFFF, Rand #262626 0,12 mm | #FFFFFF | Rand als Linie 0x10f0d |
| Fläche | 0x1100a | Verkehrsfläche | Verkehrsfläche: #FFFFFF (Autobahn #FBBF39, Durchgang #F5AE95, Verbindung #FFF582) | #FFFFFF | nur weiss, weil die Verkehrsbedeutung im Tag-Schema fehlt |
| Fläche | 0x19 | Sportplatz | Sportplatz: #E7F3E1, Rand #262626 0,12 mm | #E7F3E1 | Rand grün statt dunkel (gemeinsame Randlinie) |
| Fläche | 0xe | Hartbelagpiste | Hartbelagpiste: #FFFFFF, Rand #262626 | #FFFFFF | gleich |
| Fläche | 0x11008 | Graspiste | Graspiste: #E7F3E1, Rand #262626 | #E7F3E1 | gleich |
| Fläche | 0x1100b | Solaranlage | Solarpanel: #FFFF9B, Linien #000000 0,8 mm senkrecht und 0,6 mm waagrecht | Muster 32×32 #000000 auf #FFFF9B | gleich |
| Fläche | 0x1100d | Brücke, Staudamm | Staumauer, Staudamm: #CCCCCC, Rand #262626 | #CCCCCC | gleich |
| Fläche | 0x13 | Gebäude | Gebäude, Mauer gross, Wehr: #000000 | #000000 | gleich |
| Fläche | 0x13 | Gebäudeecken | TLM-Grundriss rechtwinklig (Abweichung im Median 0,1°) | Ecken auf das Raster der Auflösung 24 gerundet (1,6 m × 2,4 m), Abweichung im Median 4,8°, 10 % über 22° | Garmin-Grenze (IMG kennt kein feineres Raster). Offen: Ausrichtung je Gebäudegruppe vor dem Runden (Prototyp Niederuzwil: Median 1,3°, im Ortskern 0,0°), Umsetzung in vector-convert |
| Fläche | 0x1100c | Flugdach, Treibhaus | Flugdach, Treibhaus: #FFFFFF, Schraffur 45° #000000 alle 0,4 mm, Rand #333333 | Muster 32×32 #000000 auf #FFFFFF | ohne Rand |
| Fläche | 0x4b | Hintergrund | Kartengrund #FFFFFF (LK: weisses Papier) | #FFFFFF | gleich |
| Fläche | 0x11009 | Flugplatzareal | – (nicht in SMV25) | #F5F5F5 | eigene Fläche für die Übersicht |
| Fläche | 0x1100e | Siedlung (Übersicht) | – (nicht in SMV25) | #BEBEBE | Auflösung 14–21, #BEBEBE (Test 20: #DADADA zu blass) |
| Fläche | 0x1100f | Siedlung (LK50) | – (nicht in SMV25) | #F0F0F0 | Auflösung 22, sehr hell unter den Gebäuden (Test 10) |
| Punkt | 0x400 | Stadt, Kleinstadt, Dorf (0x0400/0x0800/0x0c00) | LK: Ortsname ohne Punkt, Städte in Grossbuchstaben | Garmin-Standarddarstellung (kein TYP-Eintrag) | Abweichung: Garmin zeichnet einen Ortspunkt. Mit TYP-Override zeigte BaseCamp die Namen nicht. |
| Punkt | 0xe00 | Weiler | Beschriftung ohne Symbol | nur Schrift (LargeFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0xf00 | Quartier | Beschriftung ohne Symbol | nur Schrift (LargeFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x6613 | Grat | Beschriftung ohne Symbol | nur Schrift (SmallFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x6402 | Gebäudename | Beschriftung ohne Symbol | nur Schrift (NormalFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x2000 | Autobahnausfahrt | Beschriftung ohne Symbol | nur Schrift (SmallFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x1100 | Einzelhof | Beschriftung ohne Symbol | nur Schrift (NormalFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x2800 | Flurname | Beschriftung ohne Symbol | nur Schrift (NormalFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x6602 | Gebietsname | Beschriftung ohne Symbol | nur Schrift (LargeFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x6617 | Talname | Beschriftung ohne Symbol | nur Schrift (LargeFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x6611 | Gebirge | Beschriftung ohne Symbol | nur Schrift (LargeFont) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x6612 | Massiv | Name in der Suche | unsichtbar (ohne Symbol und Schrift) | nur Suchpunkt, damit er gleichnamige Beschriftungen nicht verdeckt |
| Punkt | 0x650a | Gletschername | Beschriftung ohne Symbol | nur Schrift (NormalFont, #0088D0) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x650d | Seename | Beschriftung ohne Symbol | nur Schrift (NormalFont, #0088D0) | Schriftart und Kursivschrift nicht steuerbar (TYP kennt nur Grösse und Farbe) |
| Punkt | 0x650a | Gletschername am Säntis (Blauschnee) | LK100: Gletschername ab 1:100 000 | am GPSMAP 67 erst unter 300 m sichtbar | offen: Ursache nicht geprüft, am Säntis liegen viele Labels |
| Punkt | 0x6602 | Landschaftsname Toggenburg | LK200: Landschaftsname ab 1:200 000 | am GPSMAP 67 auf keiner Zoomstufe sichtbar | offen: Ursache nicht geprüft |
| Punkt | 0x6616 | Gipfel | Gipfel: Höhenkote #000000 0,8 mm mit weissem Rand 1,1 mm (T38) + Name, 1.10 mm = 7 px | 7×7 px | Grösse passt |
| Punkt | 0x6300 | Höhenkote | Höhenkote: Punkt #000000 0,35 mm, weisser Rand 0,5 mm, 0.50 mm = 3 px | 4×4 px | Grösse passt |
| Punkt | 0x1150f | Höhenkote | Höhenkote: Punkt #000000 0,35 mm, weisser Rand 0,5 mm, 0.50 mm = 3 px | 4×4 px | Grösse passt |
| Punkt | 0x11510 | Gipfelkote | Gipfelkote Klassen 1 und 2: Punkt #000000 0,35 mm, weisser Rand 0,5 mm, 0.50 mm = 3 px | 4×4 px | Grösse passt |
| Punkt | 0x1150d | Ortsname | – (nicht in SMV25 oder Symbol aus Areal) | 4×4 px | eigenes Symbol |
| Punkt | 0x1150e | Dorfname | – (nicht in SMV25 oder Symbol aus Areal) | 4×4 px | eigenes Symbol |
| Punkt | 0x660b | Pass, Sattel | – (nicht in SMV25 oder Symbol aus Areal) | 7×5 px | eigenes Symbol |
| Punkt | 0x6601 | Höhle | Grotte, Höhle #000000, 0.90 mm = 6 px | 11×8 px | +2 px gegenüber Soll, eigenes Pixelsymbol |
| Punkt | 0x6614 | Felsblock | Felsblock #3E3E3E, 0.55 mm = 3 px | 5×4 px | Grösse passt |
| Punkt | 0x6511 | Quelle | Quelle #0088D0, 0.90 mm = 6 px | 9×5 px | Grösse passt |
| Punkt | 0x6508 | Wasserfall | – (nicht in SMV25 oder Symbol aus Areal) | 14×10 px | eigenes Symbol |
| Punkt | 0x5000 | Brunnen | Brunnen #0088D0 auf #E6F2FF, 0.80 mm = 5 px | 5×5 px | Grösse passt |
| Punkt | 0x11503 | Gipfelkreuz | Gipfelkreuz #000000, 1.30 mm = 8 px | 7×8 px | Grösse passt |
| Punkt | 0x2c0b | Kapelle | Kapelle #000000, 0.90 mm = 6 px | 10×12 px | +6 px gegenüber Soll, eigenes Pixelsymbol |
| Punkt | 0x6404 | Kirche | Sakraler Turm #000000, 1.20 mm = 8 px | 14×14 px | +6 px gegenüber Soll, eigenes Pixelsymbol |
| Punkt | 0x11504 | Bildstock | Bildstock #000000, 1.30 mm = 8 px | 5×8 px | Grösse passt |
| Punkt | 0x11505 | Denkmal | Denkmal #000000, 1.00 mm = 6 px | 5×5 px | Grösse passt |
| Punkt | 0x2c02 | Burg, Ruine | – (nicht in SMV25 oder Symbol aus Areal) | 14×14 px | eigenes Symbol |
| Punkt | 0x2c04 | Aussichtsturm | Aussichtsturm #000000, 1.40 mm = 9 px | 14×14 px | +5 px gegenüber Soll, eigenes Pixelsymbol |
| Punkt | 0x11501 | Antenne | Antenne gross #000000, 2.04 mm = 13 px | 7×11 px | -2 px: SMV-Grösse ist die Geviert-Höhe der Symbolschrift, das Zeichen selbst ist kleiner |
| Punkt | 0x11507 | Wasserturm | Wasserturm #0088D0, 0.92 mm = 6 px | 5×5 px | Grösse passt |
| Punkt | 0x11506 | Hochkamin | Hochkamin #000000, 1.10 mm = 7 px | 5×7 px | Grösse passt |
| Punkt | 0x6411 | Turm | Turm #000000, 0.80 mm = 5 px | 5×5 px | Grösse passt |
| Punkt | 0x11502 | Windturbine | Windturbine #000000, 1.94 mm = 12 px | 9×11 px | Grösse passt |
| Punkt | 0x11508 | Triangulationspunkt | Triangulationspyramide #000000, 1.20 mm = 8 px | 7×6 px | -2 px gegenüber Soll, eigenes Pixelsymbol |
| Punkt | 0x5200 | Aussichtspunkt | – (nicht in SMV25 oder Symbol aus Areal) | 14×10 px | eigenes Symbol |
| Punkt | 0x2b04 | Berghütte | – (nicht in SMV25 oder Symbol aus Areal) | 14×11 px | eigenes Symbol |
| Punkt | 0x2b03 | Camping | Campingplatz #000000, 2.00 mm = 13 px | 11×7 px | -6 px: SMV-Grösse ist die Geviert-Höhe der Symbolschrift, das Zeichen selbst ist kleiner |
| Punkt | 0x2a00 | Gastwirtschaft | Gastgewerbe abgelegen (Fahne) #000000, 1.17 mm = 7 px | 11×11 px | +4 px gegenüber Soll, eigenes Pixelsymbol |
| Punkt | 0x2f08 | Bahnhof | Name rot (Wunsch des Benutzers), Rot #DD1919 der Bahnlinien. SMV25 hat kein Bahnhofsymbol | 15×9 px | Symbol rot 15×9, Name ab 24. Schrift #DD1919 in der TYP, das GPSMAP 67 zeichnet Punktnamen immer schwarz (belegt mit Farbtest FID 7799). Bus, Schiff und Seilbahn nur im Routen-Overlay |
| Punkt | 0x5902 | Flugplatz | – (nicht in SMV25 oder Symbol aus Areal) | 14×10 px | eigenes Symbol |
| Punkt | 0x5904 | Heliport | Heliport #000000, 2.10 mm = 13 px | 11×10 px | -3 px: SMV-Grösse ist die Geviert-Höhe der Symbolschrift, das Zeichen selbst ist kleiner |
| Punkt | 0x1150c | Einzelbaum | Einzelbaum #70B446, 0.44 mm = 3 px | 3×3 px | Grösse passt |
| Punkt | 0x1150b | Landesgrenzstein | Landesgrenzstein #C22976, 0.50 mm = 3 px | 3×3 px | Grösse passt |
| Punkt | 0x1150a | Durchfahrtssperre | Durchfahrtssperre #DD1919, 0.45 mm = 3 px | 5×2 px | Grösse passt |
| Punkt | 0x3002 | Spital | Spitalareal-Symbol #0088D0, 1.50 mm = 9 px | 14×14 px | +5 px gegenüber Soll, eigenes Pixelsymbol |

## Hinweise

- Status „gleich“: Ist entspricht dem SMV25-Soll nach Umrechnung und Rundung auf ganze Pixel.
- Jede Zeile nennt den Grund einer Abweichung. Die Garmin-Grenzen und die bewussten Abweichungen stehen gesammelt in `docs/stil/stil.md`. Garmin-Grenzen sind zum Beispiel: eine Breite je Typ, keine Schriftart, Muster 32×32 mit 2 Farben, Label-Platzierung durch das Gerät.
- Diese Typen haben dieselbe Signatur wie der Grundtyp, nur mit anderem Massstab:
  - 0x109.. (Grobstufen 12–21)
  - 0x10a.. (Übersicht 21–23)
  - 0x10b.. (LK50 21–22)
  - 0x10c.. und 0x10d.. (Auflösung 24 in Geländebreite)
- Gemessen wird der Fortschritt von style-qa gegen SMR25-Ausschnitte (Berichte dort).

## Zeichenreihenfolge der Flächen

Stufe 1 liegt unten.

- 1: 0x4b
- 2: 0x1100e, 0x1100f, 0x11009
- 3: 0x50
- 4: 0x1a, 0x17, 0x11005, 0xb, 0xc, 0x11006, 0x4e, 0x11007, 0x11003, 0x18
- 5: 0x5, 0x1100a
- 6: 0x19, 0xe, 0x11008, 0x1100b, 0x11004, 0x1100d
- 7: 0x11002, 0x11001
- 8: 0x3c, 0x3d, 0x3e, 0x3f, 0x41, 0x48, 0x4c
- 9: 0x11000, 0x4f, 0x51, 0x11010, 0x11011
- 10: 0x13, 0x1100c, 0x4d
