"""Referenz rendern: offizielles SMV25-QGIS-Projekt, headless über PyQGIS.

Läuft mit dem Python von QGIS (siehe qgis_python.sh), nicht mit dem venv:
    qgis_python.sh render_ref_qgis.py JOBS.json

JOBS.json: {"qgs": "...", "exclude": ["T28_..."], "jobs": [{"extent": [minE,minN,maxE,maxN],
            "w": 800, "h": 600, "dpi": 180, "out": "....png"}, ...]}
Die Symbolgrössen des Projekts sind in mm; mit dpi = Geräte-dpi und dem Massstab der Zoomstufe
entspricht das Bild dem, was die Landeskarte bei gleicher Darstellungsgrösse zeigen würde.
"""
import json
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qgis.core import (QgsApplication, QgsProject, QgsMapSettings, QgsRectangle,
                       QgsMapRendererParallelJob, QgsCoordinateReferenceSystem)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor


def main():
    cfg = json.load(open(sys.argv[1]))
    app = QgsApplication([], False)
    app.initQgis()
    # Liberation Sans Narrow (SMV25-Schrift, auch in den FONTNAME-Feldern der Annotationen)
    # ist unter macOS nicht installiert; Arial Narrow hat dieselben Masse.
    fm = QgsApplication.fontManager()
    for fam, rep in cfg.get('font_replace', {'Liberation Sans Narrow': 'Arial Narrow'}).items():
        fm.addFontFamilyReplacement(fam, rep)
    prj = QgsProject.instance()
    if not prj.read(cfg['qgs']):
        print('Projekt nicht lesbar:', cfg['qgs'], file=sys.stderr)
        sys.exit(2)
    root = prj.layerTreeRoot()
    layers = [l for l in root.checkedLayers()
              if not any(x in l.name() or x in l.source() for x in cfg.get('exclude', []))]
    bad = [l.name() for l in layers if not l.isValid()]
    if bad:
        print('Ungültige Layer:', bad, file=sys.stderr)
    layers = [l for l in layers if l.isValid()]
    print('Layer sichtbar:', len(layers))
    for job in cfg['jobs']:
        ms = QgsMapSettings()
        ms.setLayers(layers)
        ms.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:2056'))
        ms.setBackgroundColor(QColor(255, 255, 255))
        ms.setOutputDpi(job['dpi'])
        ms.setOutputSize(QSize(job['w'], job['h']))
        ms.setExtent(QgsRectangle(*job['extent']))
        ms.setFlag(ms.Antialiasing, True) if hasattr(ms, 'Antialiasing') else None
        r = QgsMapRendererParallelJob(ms)
        r.start()
        r.waitForFinished()
        img = r.renderedImage()
        os.makedirs(os.path.dirname(job['out']), exist_ok=True)
        img.save(job['out'], 'PNG')
        print('ok', job['out'], 'Massstab 1:%d' % round(ms.scale()))
    app.exitQgis()


if __name__ == '__main__':
    main()
