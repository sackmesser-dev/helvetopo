#!/usr/bin/env python3
"""Erzeugt src/style/routes/lines (mkgmap-Style des Routen-Overlays, FID 7702).

    python3 -I src/routes/make_style.py > src/style/routes/lines

Zoomstufen (Etappe 3, Ziel: Look der Landeskarte, Routen nur als Zusatz).
Auflösung ≈ LK-Massstab wie im Basis-Style: 24/23 ≈ 1:25 000, 22 ≈ 1:50 000,
21 ≈ 1:100 000, 20 ≈ 1:200 000.
  - Alle Routen (jedes Land, jedes Netz) und alle Wanderwege setzen auf derselben Stufe
    START_RES ein (Wunsch des Benutzers: alles verhält sich gleich, in Vektorkarte, Overlay
    und Pixel/Luftbild). Dieser Style ist die einzige Quelle, src/raster_img/routen.py nutzt
    ihn unverändert.
  - Grob (START_RES bis COARSE_MAX): Übersichtstyp des Landes (0x10e18–0x10e1d), stärker
    aufgehellt. Kein Label unter SHIELD_RES, ab SHIELD_RES nur die Routennummer im Schild.
  - Nah (ab COARSE_MAX+1): Routentyp 0x10e10–0x10e15. Name erst ab NAME_RES.
  - Wanderwege: ein Typ je Klasse ab START_RES, ohne Label.
  - Breite 3 px auf allen Stufen (TYP, src/routes/make_typ.py).
Jede Route wird mit `continue` mehrfach ins IMG geschrieben. Ohne with_actions gelten
`name`/`delete` jeweils nur für das Element dieser Regel.
"""

START_RES = 21   # erste Stufe für alle Routen und Wanderwege (≈ 1:100 000)
COARSE_MAX = 22  # letzte grobe Stufe (≈ 1:50 000)
SHIELD_RES = 22  # ab hier Routennummer im Schild
NAME_RES = 24  # ab hier Routenname dazu (Etappe 4: in der Stadt sonst zu unruhig)

# Land, Netz -> (Typ nah, Typ grob). Alle ab START_RES.
COARSE = {"wanderland": 0x10E18, "veloland": 0x10E1A, "mountainbikeland": 0x10E1B,
          "skatingland": 0x10E1C, "kanuland": 0x10E1D}
FINE = {"wanderland": 0x10E10, "veloland": 0x10E12, "mountainbikeland": 0x10E13,
        "skatingland": 0x10E14, "kanuland": 0x10E15}
ROUTES = [(land, net, FINE[land], COARSE[land]) for land in FINE
          for net in ("national", "regional", "local")]
ROUTES.insert(3, ("wanderland", "handicap", 0x10E11, COARSE["wanderland"]))
# Review 1: Routennummern müssen von Strassennummern und untereinander unterscheidbar sein.
# Abgestimmt mit style-typ (2026-11-04): Die Basis belegt interstate (Autobahn), shield
# (Autostrasse) und box (Haupt-/Durchgangsstrasse). Alle Routen bekommen `oval` mit einem
# Buchstabenpräfix je Land („W24“, „V7“, „M95“, „S3“, „K1“). Die Netzebene ergibt sich aus
# der Stellenzahl der Nummer (national 1-, regional 2-, lokal 3-stellig).
SHIELD = {land: "oval" for land in
          ("wanderland", "veloland", "mountainbikeland", "skatingland", "kanuland")}
PREFIX = {"wanderland": "W", "veloland": "V", "mountainbikeland": "M",
          "skatingland": "S", "kanuland": "K"}

TRAILS = [
    ("alpinwanderweg", 0x10E02),
    ("bergwanderweg", 0x10E01),
    ("wanderweg", 0x10E00),
]

HEADER = """\
# Routen-Overlay FID 7702 – GENERIERT von src/routes/make_style.py, nicht von Hand ändern.
# Erweiterte Linientypen (0x10e00–0x10e1f, Subtyp max. 0x1f), Darstellung im TYP
# src/style/typ/routes.txt (aus src/routes/make_typ.py). Nichts ist routingfähig.
# Im Gesamt-Build (Familie 7701) verschiebt ROUTES_TYPE_REMAP die Codes nach 0x113xx.
#
# Alle Routen und Wanderwege ab Auflösung {start}, Breite 3 px auf allen Stufen.
# Grob ({start} bis {cmax}): Übersichtstyp, stärker aufgehellt, Label erst ab {sres} (nur Nummer im Schild).
# Nah (ab {fine}): Routentyp, Label Schild, Name erst ab {nres}.
# Schild: `oval` mit Präfix W/V/M/S/K, z. B. „W24“, „V7“, „M95“.
# interstate/shield/box gehören den Strassen der Basis.
"""


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Routen-Style erzeugen")
    ap.add_argument("--part", choices=["all", "routes", "trails"], default="all",
                    help="routes = nur SchweizMobil-Routen, trails = nur Wanderwegnetz "
                         "(für getrennt schaltbare Overlays, siehe docs/vektor/routen.md)")
    part = ap.parse_args().part
    p = print
    fine = COARSE_MAX + 1
    p(HEADER.format(start=START_RES, cmax=COARSE_MAX, sres=SHIELD_RES, fine=fine, nres=NAME_RES))
    res = START_RES
    for land, net, typ, coarse in (ROUTES if part != "trails" else []):
        cond = f"ch:route={land} & ch:network={net}"
        # Präfix + Nummer im Schild; `set` gilt (ohne with_actions) nur für diese Regel
        sym = f"|highway-symbol:{SHIELD[land]}" if SHIELD[land] else ""
        shield = f"set ch:rref='{PREFIX[land]}${{ref}}'; name '${{ch:rref{sym}}}"
        if coarse is not None and res <= COARSE_MAX:
            if res < SHIELD_RES:
                p(f"{cond} {{ delete name; delete ref }} "
                  f"[0x{coarse:05x} resolution {res}-{SHIELD_RES - 1} continue]")
            p(f"{cond} & ref=* {{ {shield}' }} "
              f"[0x{coarse:05x} resolution {max(res, SHIELD_RES)}-{COARSE_MAX} continue]")
            p(f"{cond} & ref!=* {{ delete name }} "
              f"[0x{coarse:05x} resolution {max(res, SHIELD_RES)}-{COARSE_MAX} continue]")
        lo = max(res, fine)
        if lo < NAME_RES:
            p(f"{cond} & ref=* {{ {shield}' }} "
              f"[0x{typ:05x} resolution {lo}-{NAME_RES - 1} continue]")
            p(f"{cond} & ref!=* {{ delete name }} [0x{typ:05x} resolution {lo}-{NAME_RES - 1} continue]")
        hi = max(lo, NAME_RES)
        p(f"{cond} & ref=* {{ {shield} ${{name}}' }} [0x{typ:05x} resolution {hi}]")
        p(f"{cond} & ref!=* {{ name '${{name}}' }} [0x{typ:05x} resolution {hi}]")
        p("")
    if part == "routes":
        return
    p("# Wanderwege swissTLM3D, LK-artig über dem Weg: gelb-weiss = Wanderweg,")
    p("# rot-weiss = Bergwanderweg, blau-weiss = Alpinwanderweg")
    for cls, typ in TRAILS:
        p(f"ch:wanderweg={cls} [0x{typ:05x} resolution {START_RES}]")


if __name__ == "__main__":
    main()
