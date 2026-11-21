Helvetopo – Karten der Schweiz aus freien Geodaten (Stand @VERSION@, Gebiet: @AREA@)
==========================================================================================

Inoffizielles Projekt. Dies ist keine Karte von swisstopo, vom ASTRA oder von SchweizMobil.

Inhalt
------
gmapsupp.img     Vektorkarte für Garmin-Handhelds (GPSMAP, Montana, eTrex, Oregon). Wanderwege und
                 SchweizMobil-Routen liegen im Standard (DEVICE_ROUTES=overlay) im eigenen Overlay
                 "Helvetopo Routen" (FID 7702, src/raster_img/routen.py), in BaseCamp sind sie eingebaut.
                 Auf das Gerät oder die microSD-Karte in den Ordner /Garmin/ kopieren
                 (vorhandene gmapsupp.img vorher umbenennen, z. B. in swisstopo.img).
BaseCamp/        Karten für Garmin BaseCamp. Jeden *.gmap-Ordner kopieren nach
                   macOS:   ~/Library/Application Support/Garmin/Maps/
                   Windows: C:\ProgramData\Garmin\Maps\  (oder mit MapInstall)
LICENSE.txt      Lizenz und Quellenangaben.

Karten
------
Alles gehört zur Kartenfamilie "Helvetopo" (FID 7701):
  Basiskarte       Vektorkarte mit Routing, Adresssuche, Schummerung (DEM) und Höhenkoten
  Routen           Wanderwege und SchweizMobil-Routen (transparente Kacheln)
  Höhenlinien      10/20 m wie Landeskarte (transparente Kacheln oder in der Basiskarte)
Höhenlinien in diesem Build: @CONTOURS@ (overlay = eigene Kacheln, embedded = in der Basiskarte).
Gerätedatei in diesem Build: @DEVICE_FAMILIES@ (single = eine Karte; split = drei Karten
7701/7702/7703, am Gerät einzeln unter Karte > Karteninformationen schaltbar).

Hinweise
--------
- Auto-Routing ist nur topografisch (keine Einbahnen, Abbiegeverbote oder Tempolimits).
  Nicht zur Fahrzeugnavigation verwenden. Fuss- und Velorouting funktionieren.
- Bei Zielen ohne Fahrweg führt die Auto- bzw. Velo-Route am Ende über Fusswege; das ist
  Garmin-Verhalten.
- Ohne Gewähr. Für Touren im Gebirge immer zusätzlich die Landeskarte verwenden.

Quellen
-------
©swisstopo: swissTLM3D, swissNAMES3D, swissBOUNDARIES3D, swissALTI3D, swissTLM3D Wanderwege,
amtliches Gebäudeadress- und Strassenverzeichnis (Open Government Data).
Routen Wanderland, Veloland, Mountainbikeland, Skatingland:
Bundesamt für Strassen, Kanton, Stiftung SchweizMobil (Opendata BY).
Kanuland: Stiftung SchweizMobil (Open Data BY).
Erstellt mit mkgmap @MKGMAP@ und splitter (GPL), GDAL, osmium.
