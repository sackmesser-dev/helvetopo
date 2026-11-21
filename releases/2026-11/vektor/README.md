# Helvetopo Vektor 2026-11

Vektorkarte im Stil der Landeskarte 1:25'000 für Garmin-Geräte und BaseCamp. Gebiet: Schweiz und Liechtenstein.
Inoffizielle Karte: kein Produkt von swisstopo, ASTRA, SchweizMobil oder Garmin.

## Dateien
- `Helvetopo_Vektor_Schweiz_2026-11.img`: Gerätedatei (Basiskarte mit Höhenlinien, FID 7701).
  In den Ordner `Garmin/` auf dem Gerät oder der microSD-Karte kopieren.
- `Helvetopo_Routen_…img`: Wanderwege und SchweizMobil-Routen als eigenes Overlay (FID 7702).
  Ebenfalls nach `Garmin/` kopieren. Am Gerät unter Karteninformationen einzeln schaltbar. Es passt
  auch über die Pixelkarte und das Luftbild.
- `Helvetopo_Vektor_Schweiz_2026-11_BaseCamp.zip`: BaseCamp-Paket. Entpacken und den `.gmap`-Ordner kopieren nach
  `C:\ProgramData\Garmin\Maps\` (Windows) bzw. `~/Library/Application Support/Garmin/Maps/` (macOS).
  BaseCamp zeigt nur eine Karte gleichzeitig. Deshalb sind die Routen im BaseCamp-Paket eingebaut.

Die Prüfsummen stehen in `Helvetopo_2026-11_SHA256SUMS.txt`.

## Routing
- Fuss und Velo aus swissTLM3D und den SchweizMobil-Routen. Wanderwege werden bevorzugt.
- **Velo/MTB:** im Aktivitätsprofil „Mautstrassen vermeiden“ einschalten. Die Karte nutzt das
  Maut-Merkmal als Hinweis auf Haupt- und Kantonsstrassen ohne Veloroute. So folgt die Route
  bevorzugt Veloland.
- **Auto und Wandern:** „Mautstrassen vermeiden“ ausschalten. Die Karte kennt keine Mautgebühren.
- Auto-Routing ist nur topografisch (keine Einbahnen, Abbiegeverbote, Tempolimits) und nicht zur
  Fahrzeugnavigation geeignet.

## Quellen und Lizenz
Quellenangaben: `©swisstopo`. Routen: `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`.
Kanuland: `Stiftung SchweizMobil`. Datenstand: [QUELLSTAND.md](QUELLSTAND.md).
Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md). Ohne Gewähr.
