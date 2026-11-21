{title}
{underline}

Garmin Custom Map (KMZ) aus der Landeskarte der Schweiz (Swiss Map Raster 1:{scale}'000).

Quelle und Lizenz
-----------------
Kartendaten: ©swisstopo
Swiss Map Raster 1:{scale}'000, Ausgabe {years}, Bundesamt für Landestopografie swisstopo.
Open Government Data (OGD), Nutzungsbedingungen:
https://www.swisstopo.admin.ch/ogd-conditions
Die Daten wurden umprojiziert (LV95 → WGS84), neu abgetastet und als JPEG gekachelt.
Dies ist keine offizielle Karte von swisstopo. Erzeugt vom Projekt Helvetopo.

Inhalt
------
Datei:        {kmz}
Gebiet:       {west}–{east}° O, {south}–{north}° N (WGS84)
Auflösung:    {res} m/Pixel
Kacheln:      {tiles} JPEG-Kacheln (max. 1024 × 1024 px, Baseline-JPEG)
Grösse:       {kmz_mb} MB
Draw Order:   {draw_order} (über 50: wird über Garmin-Vektorkarten gezeichnet)

Installation
------------
1. Gerät per USB verbinden (GPSMAP 66/67, Montana 700/710/750i u. a.).
2. KMZ-Datei in den Ordner Garmin/CustomMaps/ kopieren (interner Speicher oder SD-Karte;
   den Ordner bei Bedarf anlegen).
3. Gerät trennen und neu starten.
4. Karte einschalten: Einstellungen → Karte → Karteninformationen/Kartenmanager →
   Custom Maps (je nach Modell). Vektorkarten mit eigener Fläche (z. B. TopoActive)
   bei Bedarf ausblenden, wenn die Pixelkarte überdeckt wird.

Grenzen der Geräte
------------------
- Garmin zählt die Kacheln aller Custom Maps auf dem Gerät zusammen. GPSMAP 66/67 und
  Montana 7xx: 500 Kacheln gesamt, viele ältere oder kleinere Geräte: 100.
  Diese Datei hat {tiles} Kacheln. Wer mehrere KMZ installiert, muss die Summe beachten.
- Beim Herauszoomen blendet das Gerät Custom Maps je nach Modell aus oder zeichnet langsam.
