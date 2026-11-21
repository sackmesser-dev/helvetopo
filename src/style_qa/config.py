"""Gemeinsame Einstellungen der Stil-Qualitätskontrolle (style_qa).

Alle Bilder eines Ausschnitts und einer Zoomstufe liegen auf demselben LV95-Raster
(EPSG:2056, nordorientiert, gleiche Pixelgrösse), damit sie pixelweise vergleichbar sind.
"""
import glob
import os
import sys

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

MAIN = str(paths.MAIN)
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

DOWNLOADS = str(paths.DOWNLOADS)                                 # HELVETOPO_DATA
SMV25_DIR = os.path.join(DOWNLOADS, 'smv25', 'merged')          # von merge_smv25.sh
SMV25_GPKG = os.path.join(SMV25_DIR, 'SMV25_CHLV95LN02.gpkg')
QGS_ORIG = os.path.join(DOWNLOADS, 'style-swisstopo', 'hilfsdateien', 'Hilfsdateien-GPKG',
                        'SMV25_CHLV95LN02.qgs')
SMR_DIR = os.path.join(DOWNLOADS, 'smr')
# QGIS-App-Bundle: QGIS_APP setzen, sonst das neueste /Applications/QGIS*.app.
_qgis = sorted(glob.glob('/Applications/QGIS*.app/Contents'))
QGIS_APP = os.environ.get('QGIS_APP', _qgis[-1] if _qgis else '')

# Stil-Quelle: Checkout mit src/style/… und work/style/testgebiet. Vorgabe: Haupt-Checkout,
# ein anderer Checkout oder Worktree über STYLE_ROOT.
STYLE_ROOT = os.environ.get('STYLE_ROOT', MAIN)
RENDER_IMG = os.environ.get('RENDER_IMG', os.path.join(STYLE_ROOT, 'src', 'style', 'tools', 'render_img.py'))
TYP_TXT = os.environ.get('TYP_TXT', os.path.join(STYLE_ROOT, 'src', 'style', 'typ', 'swisstopo.txt'))
IMG_DIR = os.environ.get('IMG_DIR', os.path.join(STYLE_ROOT, 'work', 'style', 'testgebiet'))

# Overlays (Name, IMG-Ordner, TYP-Quelltext), die über die Basiskarte gelegt werden.
# Umgebungsvariable OVERLAYS="name=ordner:typ;…" ersetzt die Vorgabe, OVERLAYS="" schaltet ab.
OVERLAYS = [('hoehen7703', os.path.join(MAIN, 'work', 'dem', 'img7703'),
             os.path.join(MAIN, 'src', 'style', 'typ', 'contours.txt'))]
if 'OVERLAYS' in os.environ:
    OVERLAYS = [(x.split('=')[0], *x.split('=', 1)[1].split(':')) for x in os.environ['OVERLAYS'].split(';') if x]

# Messziel: 'style' (Stil-Testbuild unter STYLE_ROOT, Vorgabe) oder 'gesamt' (Gesamt-Build in main,
# src/build/build_all.sh → work/build/: Basis mit DEM und Höhenkoten, Höhenlinien-Kacheln 77012001,
# gemeinsame TYP meta/ch_7701.txt). Routen-Kacheln (77011001) bleiben weg: die LK zeigt keine Routen.
TARGET = os.environ.get('QA_TARGET', 'style')
if TARGET == 'gesamt':
    _B = os.path.join(MAIN, 'work', 'build')
    IMG_DIR = os.environ.get('IMG_DIR', os.path.join(_B, '7701'))
    TYP_TXT = os.environ.get('TYP_TXT', os.path.join(_B, 'meta', 'ch_7701.txt'))
    # Höhenlinien-Kacheln nur, wenn sie zum aktuellen Build gehören (CONTOURS=overlay). Bei
    # CONTOURS=embedded (Standard seit 2026-11-04) stecken sie in den Basiskacheln; der Ordner
    # 7701-contours kann dann von einem älteren Build übrig sein.
    def _mt(d):
        import glob as _g
        fs = [f for f in _g.glob(os.path.join(d, '7*.img')) if not f.endswith('0000.img')]
        return max((os.path.getmtime(f) for f in fs), default=0)
    _c = os.path.join(_B, '7701-contours')
    OVERLAYS = [('hoehen', _c, TYP_TXT)] if _mt(_c) >= _mt(IMG_DIR) - 600 else []
    if os.environ.get('QA_ROUTES') == 'yes':
        OVERLAYS.append(('routen', os.path.join(_B, '7701-routes'), TYP_TXT))

# BaseCamp-Screenshots, die der Bericht nur auflistet (Ordner per Umgebungsvariable wählbar)
BASECAMP_SHOTS = os.environ.get('STYLE_QA_BASECAMP_SHOTS', os.path.join(MAIN, 'work', 'basecamp-shots'))
REF_OUT = os.environ.get('STYLE_QA_REF', os.path.join(REPO, 'work', 'style_qa'))      # Referenzen (gemeinsam)
OUT = os.environ.get('STYLE_QA_OUT', os.path.join(REPO, 'work', 'style_qa', *(['gesamt'] if TARGET == 'gesamt' else [])))

# Gerät: GPSMAP 66/67 (240x400 px auf 3") ≈ 0,163 mm/px. Projektkonvention (docs/stil/soll-ist.md):
# px = round(mm × 6,25), also 0,16 mm je Gerätepixel ≈ 159 dpi; 1:25 000 ≈ 4 m/px.
MM_PER_PX = 0.16
DEVICE_DPI = 25.4 / MM_PER_PX          # 158,75 dpi

# Zoomstufen: Massstab, wie er am Gerät erscheint (Gerätepixel = 0,16 mm).
# res = Garmin-Auflösung, die der Style dieser Stufe zuordnet (src/style/swisstopo/options).
# refs = Referenzen in der Reihenfolge ihres Gewichts.
ZOOMS = {
    'z12k':  {'scale': 12500,  'res': 24, 'refs': ['smv25', 'smr25'], 'label': "1:12'500 (Auflösung 24)"},
    'z25k':  {'scale': 25000,  'res': 23, 'refs': ['smv25', 'smr25'], 'label': "1:25'000 (Auflösung 23)"},
    'z50k':  {'scale': 50000,  'res': 22, 'refs': ['smr50', 'smv25'], 'label': "1:50'000 (Auflösung 22)"},
    'z100k': {'scale': 100000, 'res': 21, 'refs': ['smr100'], 'label': "1:100'000 (Auflösung 21)"},
}
# lk = Massstab der LK, deren Strichbreiten in dieser Stufe als Soll gelten (Geländebreite):
#      Soll px = mm × k mit k = lk / 1000 / mpx (1 mm LK25 = 25 m Gelände).
# SMV25 wird mit Referenzmassstab lk gerendert (dpi = 25,4 × k), bei 1:12 500 also als vergrösserte
# LK25 – wie die SMR25 in derselben Stufe.
LK_SCALE = {'z12k': 25000, 'z25k': 25000, 'z50k': 50000, 'z100k': 100000}
for zk, z in ZOOMS.items():
    z['mpx'] = z['scale'] * MM_PER_PX / 1000.0      # Meter je Pixel
    z['lk'] = LK_SCALE[zk]
    z['k'] = z['lk'] / 1000.0 / z['mpx']            # Soll-px je LK-mm
    z['dpi'] = 25.4 * z['k']

# Ausschnitte: Mittelpunkt LV95, Bildgrösse in Pixel (Montana-Hochformat ist 480x800,
# hier ein etwas grösseres Querformat für mehr Messpunkte).
W, H = 800, 600
CUTOUTS = {
    'stgallen':  {'name': 'St. Gallen Zentrum', 'e': 2746220, 'n': 1254440},
    'herisau':   {'name': 'Herisau', 'e': 2738950, 'n': 1249960},
    'wil':       {'name': 'Wil SG', 'e': 2721420, 'n': 1257970},
    'saentis':   {'name': 'Säntis/Alpstein', 'e': 2744180, 'n': 1234910},
    'landwirtschaft': {'name': 'Wald/Landwirtschaft Oberbüren–Niederuzwil', 'e': 2730670, 'n': 1252460},
}


def grid(cut, zoom):
    """(minE, minN, maxE, maxN, W, H, mpx) des Zielrasters."""
    c = CUTOUTS[cut]
    z = ZOOMS[zoom]
    mpx = z['mpx']
    w2, h2 = W * mpx / 2, H * mpx / 2
    return (c['e'] - w2, c['n'] - h2, c['e'] + w2, c['n'] + h2, W, H, mpx)


def ref_path(*parts):
    p = os.path.join(REF_OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def path(*parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p
