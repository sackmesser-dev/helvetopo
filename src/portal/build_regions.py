#!/usr/bin/env python3
"""Erzeugt prototype/regions.json: Umrisse der Download-Gebiete als SVG-Pfade für die kleine Schweizerkarte.

Quelle der Gebiete sind die tatsächlichen Zellflächen der Pixel-Teilung (GeoJSON aus dem Build,
WGS84, Features mit id, varianten, zellen). Die Grenzen folgen dem Kachelgitter, nicht den Kantonen.
Dazu kommt die Landesgrenze (Schweiz und Liechtenstein) aus swissBOUNDARIES3D zur Orientierung.

Aufruf (GDAL und shapely aus dem venv):
    .venv/bin/python -I src/portal/build_regions.py [--geojson A.geojson --geojson B.geojson]

Ohne --geojson liest es alle Standarddateien (Pixel-Regionen und Luftbild-Detail). Jede ID darf nur einmal vorkommen.
"""
import argparse
import json
import os
import sys

from osgeo import ogr, osr
import numpy as np
import shapely
from shapely import wkb
from shapely.geometry import shape
from shapely.ops import unary_union

ogr.UseExceptions()
osr.UseExceptions()

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import paths  # noqa: E402

GEOJSON_DEFAULT = [os.path.join(HERE, "data", n) for n in
                   ("pixel-regionen-2026-11.geojson", "luftbild-detail-2026-11.geojson")]
SIMPLIFY_M = 500
WIDTH = 400


def to_lv95():
    src, dst = osr.SpatialReference(), osr.SpatialReference()
    src.ImportFromEPSG(4326)
    dst.ImportFromEPSG(2056)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(src, dst)

    return lambda geom: shapely.transform(geom, lambda a: np.array(ct.TransformPoints(a.tolist()))[:, :2])


def country():
    ds = ogr.Open(str(paths.BOUNDARIES_GPKG))
    lyr = ds.GetLayerByName("tlm_landesgebiet")
    lyr.SetAttributeFilter("icc IN ('CH', 'LI')")
    return unary_union([wkb.loads(bytes(f.GetGeometryRef().ExportToWkb())) for f in lyr]).buffer(1).buffer(-1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", action="append", help="mehrfach möglich")
    args = ap.parse_args()
    sources = args.geojson or GEOJSON_DEFAULT

    proj = to_lv95()
    feats = [f for src in sources for f in json.load(open(src, encoding="utf-8"))["features"]]
    ids = [f["properties"]["id"] for f in feats]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        sys.exit(f"doppelte IDs: {dup}")
    areas = {f["properties"]["id"]: proj(shape(f["geometry"])) for f in feats}
    meta = {f["properties"]["id"]: {"varianten": f["properties"].get("varianten", []),
                                    "zellen": f["properties"].get("zellen")} for f in feats}
    land = country()

    allg = unary_union(list(areas.values()) + [land])
    minx, miny, maxx, maxy = allg.bounds
    scale = WIDTH / (maxx - minx)
    height = round((maxy - miny) * scale)

    def path(geom, simplify=0):
        g = geom.simplify(simplify, preserve_topology=True) if simplify else geom
        out = []
        for p in getattr(g, "geoms", [g]):
            if p.area < 4e6:          # kleine Splitter weglassen
                continue
            for ring in [p.exterior, *p.interiors]:
                pts = [f"{(x - minx) * scale:.1f} {(maxy - y) * scale:.1f}" for x, y, *_ in ring.coords]
                out.append("M" + "L".join(pts) + "Z")
        return "".join(out)

    data = {
        "viewBox": f"0 0 {WIDTH} {height}",
        "source": [os.path.basename(s) for s in sources],
        "outline": path(land, SIMPLIFY_M),
        "areas": {aid: path(g) for aid, g in areas.items()},
        "meta": meta,
    }
    out = os.path.join(HERE, "prototype", "regions.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{out} geschrieben ({os.path.getsize(out) // 1024} KB, {len(areas)} Gebiete)")


if __name__ == "__main__":
    main()
