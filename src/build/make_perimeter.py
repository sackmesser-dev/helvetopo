#!/usr/bin/env python3
"""Perimeter Schweiz + Liechtenstein aus swissBOUNDARIES3D (©swisstopo) als osmosis-.poly.

Erzeugt im Ausgabeordner:
  ch_fl.poly        WGS84, gepuffert (Standard 300 m), für mkgmap --dem-poly, splitter --polygon-file
  ch_fl.geojson     dasselbe zur Kontrolle
  bbox.txt          W,S,E,N (WGS84) des Perimeters

  python3 -I src/build/make_perimeter.py --out work/perimeter [--buffer 300] [--simplify 25]
Enklaven (Büsingen, Campione d'Italia) bleiben als Löcher erhalten ('!'-Ringe im .poly).
"""
import argparse
import json
import os
import sys

from osgeo import ogr, osr

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

ogr.UseExceptions()


def drop_small_holes(geom, min_area):
    """Kleine Löcher (Puffer-Artefakte) entfernen: splitter lehnt winzige Ringe als ungültig ab."""
    polys = [geom.GetGeometryRef(i).Clone() for i in range(geom.GetGeometryCount())] \
        if geom.GetGeometryType() in (ogr.wkbMultiPolygon, ogr.wkbMultiPolygon25D) else [geom.Clone()]
    out = ogr.Geometry(ogr.wkbMultiPolygon)
    for p in polys:
        q = ogr.Geometry(ogr.wkbPolygon)
        q.AddGeometry(p.GetGeometryRef(0))
        for r in range(1, p.GetGeometryCount()):
            ring = p.GetGeometryRef(r)
            h = ogr.Geometry(ogr.wkbPolygon); h.AddGeometry(ring)
            if h.GetArea() >= min_area:
                q.AddGeometry(ring)
        out.AddGeometry(q)
    return out.GetGeometryRef(0).Clone() if out.GetGeometryCount() == 1 else out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundaries", default=str(paths.DOWNLOADS / "swissboundaries3d/swissBOUNDARIES3D_1_5_LV95_LN02.gpkg"))
    ap.add_argument("--out", default="work/perimeter")
    ap.add_argument("--buffer", type=float, default=300.0, help="Puffer in m (LV95)")
    ap.add_argument("--simplify", type=float, default=25.0, help="Vereinfachung in m")
    ap.add_argument("--icc", default="CH,LI")
    ap.add_argument("--min-hole", type=float, default=200_000.0, help="kleinere Löcher entfernen (m²)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    ds = ogr.Open(a.boundaries)
    lyr = ds.GetLayerByName("tlm_landesgebiet")
    codes = a.icc.split(",")
    lyr.SetAttributeFilter("icc IN (" + ",".join(f"'{c}'" for c in codes) + ")")
    union = None
    for f in lyr:
        g = f.GetGeometryRef().Clone()
        g.FlattenTo2D()
        union = g if union is None else union.Union(g)
    geom = union.Buffer(a.buffer).SimplifyPreserveTopology(a.simplify)
    geom = drop_small_holes(geom, a.min_hole)

    src = osr.SpatialReference(); src.ImportFromEPSG(2056)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(4326); dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    geom.Transform(osr.CoordinateTransformation(src, dst))

    polys = [geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())] \
        if geom.GetGeometryType() in (ogr.wkbMultiPolygon, ogr.wkbMultiPolygon25D) else [geom]
    lines, n = ["ch_fl"], 0
    for p in polys:
        for r in range(p.GetGeometryCount()):
            ring = p.GetGeometryRef(r)
            n += 1
            lines.append(("!" if r else "") + str(n))
            lines += [f"   {x:.7f} {y:.7f}" for x, y in ring.GetPoints()]
            lines.append("END")
    lines.append("END")
    with open(os.path.join(a.out, "ch_fl.poly"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(a.out, "ch_fl.geojson"), "w") as f:
        json.dump({"type": "Feature", "properties": {"source": "swissBOUNDARIES3D ©swisstopo"},
                   "geometry": json.loads(geom.ExportToJson())}, f)
    w, e, s, nn = geom.GetEnvelope()
    with open(os.path.join(a.out, "bbox.txt"), "w") as f:
        f.write(f"{w:.5f},{s:.5f},{e:.5f},{nn:.5f}\n")
    print(f"{len(polys)} Polygon(e), {n} Ringe, BBox {w:.4f},{s:.4f},{e:.4f},{nn:.4f}")


if __name__ == "__main__":
    main()
