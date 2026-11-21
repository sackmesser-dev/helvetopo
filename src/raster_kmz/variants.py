"""Vordefinierte KMZ-Varianten für das Testgebiet (WGS84 9.00–9.50° O / 47.20–47.50° N).

Kachelbudget (siehe docs/raster/kmz.md): GPSMAP 66/67 und Montana 7xx laut Garmin-Spezifikation
500 Custom-Map-Kacheln gesamt auf dem Gerät; ältere/kleinere Geräte 100.
- *-smr25: volle Auflösung SMR25 (1,25 m/px) nur für Teilausschnitte.
- testgebiet-smr50: ganzes Testgebiet in SMR50-Originalauflösung (2,5 m/px), < 500 Kacheln.
- testgebiet-smr100: ganzes Testgebiet als Übersicht (5 m/px), < 100 Kacheln.
"""

TESTGEBIET = (9.00, 47.20, 9.50, 47.50)

VARIANTS = {v["name"]: v for v in [
    {
        # 10 × 10 Kacheln: Säntis bis Hoher Kasten, Schwägalp bis Brülisau. Passt auch auf
        # Geräte mit 100-Kachel-Limit.
        "name": "alpstein-smr25",
        "title": "Alpstein SMR25",
        "scale": 25, "res": 1.25,
        "bbox": (9.315, 47.200, 9.484, 47.315),
        "draw_order": 53,
    },
    {
        # St. Gallen bis Säntis in voller Auflösung, 391 Kacheln: zusammen mit testgebiet-smr100
        # (56) unter 500 (GPSMAP 66/67, Montana 7xx).
        "name": "stgallen-alpstein-smr25",
        "title": "St. Gallen–Alpstein SMR25",
        "scale": 25, "res": 1.25,
        "bbox": (9.212, 47.200, 9.500, 47.460),
        "draw_order": 53,
    },
    {
        "name": "testgebiet-smr50",
        "title": "Wil–St. Gallen–Alpstein SMR50",
        "scale": 50, "res": 2.5,
        "bbox": TESTGEBIET,
        "draw_order": 52,
    },
    {
        "name": "testgebiet-smr100",
        "title": "Wil–St. Gallen–Alpstein SMR100",
        "scale": 100, "res": 5.0,
        "bbox": TESTGEBIET,
        "draw_order": 51,
    },
]}
