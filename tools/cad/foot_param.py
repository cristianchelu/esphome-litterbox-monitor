import os, sys, math, importlib
import FreeCAD as App, Part, Sketcher
from FreeCAD import Vector as V

# Load-cell foot as a PartDesign document: one Params spreadsheet, one Body per part, and a feature timeline in each
# (sketch -> Pad / Pocket / Fillet / Mirrored / AdditivePipe) that can be scrubbed and edited in the GUI. Run once to
# build the tree; after that the .FCStd is the design and this script is only the record of how it was made.
# Same frame as foot.py: origin at the foot centre, +Z toward the floor, MDF face at Z = -Plate (below the base plate).

CAD = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'
if CAD not in sys.path: sys.path.insert(0, CAD)
import pdlib; importlib.reload(pdlib)
from pdlib import *

PARAMS = [
 ("Outline", None, None),
 ("BaseL",    55.0, "base/cap outline, X"),
 ("BaseW",    50.0, "base/cap outline, Y"),
 ("CornerR",  15.0, "outline corner radius"),
 ("Plate",     1.5, "base plate thickness"),
 ("Wall",      1.5, "outer wall and ribs"),
 ("WallH",     3.6, "wall/rib top above the plate top (Z=0)"),
 ("Clr",       0.1, "print-to-print clearance"),
 ("ClrMetal",  0.2, "clearance around the aluminium body"),
 ("Screws", None, None),
 ("ScrewX",   17.5, "screw pattern half pitch, X"),
 ("ScrewY",   15.0, "screw pattern half pitch, Y"),
 ("Shank",     3.8, "screw shank hole"),
 ("Head",      7.5, "screw head recess"),
 ("HeadFloor", 1.3, "recess floor above the boss bottom"),
 ("MouthR",    1.0, "round-over on the recess mouths"),
 ("BossD",     9.5, "cap boss diameter"),
 ("Cap", None, None),
 ("CapT",      1.5, "cap plate thickness"),
 ("CapEdgeR",  1.0, "round-over on the cap plate's top edge"),
 ("HouseH",    4.5, "housing height above the cap plate"),
 ("HouseIX",  12.6, "housing half-size at the S-curve inflection (mid height)"),
 ("HouseIR",   7.6, "housing corner radius there"),
 ("HouseFR",   3.0, "convex top round-over = concave base fillet (tangent S)"),
 ("CoreS",    13.0, "square filling the housing ring (the cavity ceiling is what's left of it)"),
 ("RampX_1",  15.5, "wire wedge under the cap: cavity wall -> here"),
 ("RampHY",    4.0, "wire wedge half width"),
 ("RampZ",     1.93,"wire wedge rise at the cavity wall"),
 ("CavS",     22.0, "cavity over the strain section / foot block"),
 ("CavR",      6.0, "cavity corner radius"),
 ("CavCeil",   1.5, "cavity ceiling thickness"),
 ("Load cell", None, None),
 ("CellS",    26.0, "cell body square"),
 ("CellT",     1.6, "cell body thickness"),
 ("CellR",     6.5, "cell body corner radius"),
 ("CellX_0", -14.5, "cell body -X edge"),
 ("CellX_1", "=CellX_0 + CellS", "cell body +X edge"),
 ("WinX_0",  -12.5, "cell window -X edge"),
 ("WinX_1",    6.5, "cell window +X edge"),
 ("WinHY",    10.5, "cell window half height"),
 ("WinR",      4.0, "cell window corner radius"),
 ("PlatH",     2.0, "platform the cell sits on, above the plate top"),
 ("BiteD",     8.0, "wire drop at the platform's +X edge"),
 ("BiteX",    14.2, "wire drop centre X"),
 ("RibY_0",    5.0, "Y rib pair: inner edge"),
 ("RibY_1",    6.5, "Y rib pair: outer edge"),
 ("RibXa_0",  -8.0, "X rib pair A: -X edge"),
 ("RibXa_1",  -6.5, "X rib pair A: +X edge"),
 ("RibXb_0",   3.5, "X rib pair B: -X edge"),
 ("RibXb_1",   5.0, "X rib pair B: +X edge"),
 ("ExitX_0",  20.5, "wire exit notch starts here, runs out under the +X wall"),
 ("ExitHY",    5.0, "wire exit half width"),
 ("ButtonD",  10.5, "plastic foot button"),
 ("ButtonH",   6.5, "plastic foot button height"),
 ("FootBlkX", 11.0, "foot block"),
 ("FootBlkY", 19.5, "foot block"),
 ("FootBlkZ",  3.0, "foot block"),
 ("HoleD",    "=ButtonD + 1", "cap hole for the button"),
 ("ShimT",     1.0, "levelling shim thickness"),
 ("Derived", None, None),
 ("CapZ_0",   "=WallH", "cap plate underside sits on the wall tops"),
 ("CapTop",   "=CapZ_0 + CapT", "cap plate top = housing base"),
 ("HouseTop", "=CapTop + HouseH", "housing top"),
 ("CavTop",   "=HouseTop - CavCeil", "cavity ceiling underside"),
 ("BossZ_0",  "=Clr + 0.1", "boss bottom: clear of the base's wall tops"),
 ("FootZ",    "=PlatH + CellT", "cell top face = foot block bottom"),
]
doc, ss = init("LoadCellFootParam", PARAMS)
vals = pdlib.vals

# ================= BASE =================
base = doc.addObject("PartDesign::Body", "Base")
sk = sketch(base, "BaseOutline", "XY_Plane", "-Params.Plate")
rrect(sk, "-Params.BaseL / 2", "Params.BaseL / 2", "-Params.BaseW / 2", "Params.BaseW / 2", "Params.CornerR")
pad(base, sk, "BaseBlock", "Params.Plate + Params.WallH")
sk = sketch(base, "HollowOutline", "XY_Plane", "Params.WallH")
rrect(sk, "-Params.BaseL / 2 + Params.Wall", "Params.BaseL / 2 - Params.Wall", "-Params.BaseW / 2 + Params.Wall", "Params.BaseW / 2 - Params.Wall", "Params.CornerR - Params.Wall")
pocket(base, sk, "Hollow", "Params.WallH")
sk = sketch(base, "PlatformOutline", "XY_Plane", "0")
rrect(sk, "Params.CellX_0 - Params.ClrMetal", "Params.CellX_1 + Params.ClrMetal", "-Params.CellS / 2 - Params.ClrMetal", "Params.CellS / 2 + Params.ClrMetal", "Params.CellR + Params.ClrMetal")
pad(base, sk, "Platform", "Params.PlatH")
sk = sketch(base, "PlatformCutouts", "XY_Plane", "Params.PlatH")
rrect(sk, "Params.WinX_0", "Params.WinX_1", "-Params.WinHY", "Params.WinHY", "Params.WinR", "_win")
circle(sk, "Params.BiteX", "0", "Params.BiteD", "_bite")
pocket(base, sk, "PlatformWindow", "Params.PlatH")
sk = sketch(base, "RibProfiles", "XY_Plane", "0")      # the +Y rib pair and the -Y half of the X pairs; mirrored below
rect(sk, "-Params.BaseL / 2 + Params.Wall - 0.01", "Params.CellX_0 - Params.ClrMetal", "Params.RibY_0", "Params.RibY_1", "_y_out")
rect(sk, "Params.CellX_1 + Params.ClrMetal", "Params.BaseL / 2 - Params.Wall + 0.01", "Params.RibY_0", "Params.RibY_1", "_y_in")
rect(sk, "Params.RibXa_0", "Params.RibXa_1", "-Params.BaseW / 2 + Params.Wall - 0.01", "-Params.CellS / 2 - Params.ClrMetal", "_x_a")
rect(sk, "Params.RibXb_0", "Params.RibXb_1", "-Params.BaseW / 2 + Params.Wall - 0.01", "-Params.CellS / 2 - Params.ClrMetal", "_x_b")
ribs = pad(base, sk, "Ribs", "Params.WallH")
mirrored(base, ribs, "RibsMirrored", "XZ_Plane")
sk = sketch(base, "WireExitProfile", "XY_Plane", "0")
rect(sk, "Params.ExitX_0", "Params.BaseL / 2 + 1", "-Params.ExitHY", "Params.ExitHY")
pocket(base, sk, "WireExit")
sk = sketch(base, "ScrewHoleOutlines", "XY_Plane", "0")
circles4(sk, "Params.Shank", "Params.ScrewX", "Params.ScrewY")
pocket(base, sk, "ScrewHoles")
finish(base, (0.93, 0.92, 0.88))

# ================= CAP =================
cap = doc.addObject("PartDesign::Body", "Cap")
sk = sketch(cap, "CapOutline", "XY_Plane", "Params.CapZ_0")
rrect(sk, "-Params.BaseL / 2", "Params.BaseL / 2", "-Params.BaseW / 2", "Params.BaseW / 2", "Params.CornerR")
plate = pad(cap, sk, "CapPlate", "Params.CapT")
ztop = vals["CapTop"]
fillet(cap, plate, "CapEdge", "Params.CapEdgeR", lambda e: abs(e.BoundBox.ZMin - ztop) < 1e-6 and abs(e.BoundBox.ZMax - ztop) < 1e-6)

# housing: S-profile swept around the rounded square at the inflection height. The profile sits at the start of the
# path (the -Y flat, at its -X end) in the YZ plane; the solver places the two R arcs from tangency alone.
h, r, R = vals["HouseIX"], vals["HouseIR"], vals["HouseFR"]
zb, zt = vals["CapTop"], vals["HouseTop"]
zi = (zb + zt) / 2; dz = (zt - zb) / 2; dy = math.sqrt(R**2 - (dz - R)**2)
yt, yb = -h + dy, -h - dy
path = sketch(cap, "HousingPath", "XY_Plane", "(Params.CapTop + Params.HouseTop) / 2")
rrect(path, "-Params.HouseIX", "Params.HouseIX", "-Params.HouseIX", "Params.HouseIX", "Params.HouseIR")
prof = sketch(cap, "HousingProfile", "YZ_Plane", "0")
F = Frame(prof, (1, 2))
E(prof, "AttachmentOffset.Base.z", "%s(Params.HouseIX - Params.HouseIR)" % ("-" if F.normal_sign > 0 else ""))
def arc(c, rad, a1, a2):
    return prof.addGeometry(Part.ArcOfCircle(Part.Circle(F.P(*c), V(0, 0, 1), rad), math.radians(a1), math.radians(a2)), False)
a_i1 = math.degrees(math.atan2(zi - (zt - R), -h - yt))
a_i2 = math.degrees(math.atan2(zi - (zb + R), -h - yb))
if F.reflected: a_i1, a_i2 = -a_i1, -a_i2            # a reflected frame runs the arcs the other way
sv = F.s[1]
top_arc = arc((yt, zt - R), R, 90 * sv, a_i1)        # from the top flat to the inflection
bot_arc = arc((yb, zb + R), R, -90 * sv, a_i2)       # from the base to the inflection
L = lambda a, b: prof.addGeometry(Part.LineSegment(F.P(*a), F.P(*b)), False)
l_down = L((yb, zb), (yb, zb - 0.1))
l_in   = L((yb, zb - 0.1), (-6.0, zb - 0.1))
l_up   = L((-6.0, zb - 0.1), (-6.0, zt))
l_top  = L((-6.0, zt), (yt, zt))
C = lambda *a: prof.addConstraint(Sketcher.Constraint(*a))
C("Tangent", l_top, 2, top_arc, 1)                   # flat top runs tangent into the round-over
C("Tangent", top_arc, 2, bot_arc, 2)                 # S: convex meets concave tangent at the inflection
C("Coincident", bot_arc, 1, l_down, 1); C("Coincident", l_down, 2, l_in, 1); C("Coincident", l_in, 2, l_up, 1); C("Coincident", l_up, 2, l_top, 1)
C("Horizontal", l_top); C("Horizontal", l_in); C("Vertical", l_down); C("Vertical", l_up)
C("Vertical", bot_arc, 3, bot_arc, 1)                # base point straight below its centre: the fillet lands flat on the plate
i = C("Radius", top_arc, R); prof.renameConstraint(i, "r_top"); E(prof, ".Constraints.r_top", "Params.HouseFR")
i = C("Radius", bot_arc, R); prof.renameConstraint(i, "r_base"); E(prof, ".Constraints.r_base", "Params.HouseFR")
dist_constraint(prof, "DistanceX", -1, 1, top_arc, 2, F.u("-Params.HouseIX"), "inflection")
dist_constraint(prof, "DistanceY", -1, 1, l_top, 1, F.w("Params.HouseTop"), "z_top")
dist_constraint(prof, "DistanceY", -1, 1, bot_arc, 1, F.w("Params.CapTop"), "z_base")
dist_constraint(prof, "DistanceY", l_in, 1, l_down, 1, F.w("0.1"), "bury")
dist_constraint(prof, "DistanceX", -1, 1, l_in, 2, F.u("-Params.CoreS / 2 + 0.5"), "inner")
pipe(cap, prof, path, "Housing")
sk = sketch(cap, "CoreOutline", "XY_Plane", "Params.CapTop")
rect(sk, "-Params.CoreS / 2", "Params.CoreS / 2", "-Params.CoreS / 2", "Params.CoreS / 2")
pad(cap, sk, "HousingCore", "Params.HouseH")
sk = sketch(cap, "CavityOutline", "XY_Plane", "Params.CavTop")
rrect(sk, "-Params.CavS / 2", "Params.CavS / 2", "-Params.CavS / 2", "Params.CavS / 2", "Params.CavR")
pocket(cap, sk, "Cavity")
sk = sketch(cap, "ButtonHoleOutline", "XY_Plane", "Params.HouseTop")
circle(sk, "0", "0", "Params.HoleD")
pocket(cap, sk, "ButtonHole")
# wire wedge: triangle in the XZ plane, pocketed both ways in Y, then mirrored to the -X side
wsk = sketch(cap, "WedgeProfile", "XZ_Plane", "0")
F = Frame(wsk, (0, 2))
cs, z0, rx, rz = vals["CavS"] / 2, vals["CapZ_0"] - 0.01, vals["RampX_1"], vals["RampZ"]
Lw = lambda a, b: wsk.addGeometry(Part.LineSegment(F.P(*a), F.P(*b)), False)
w1 = Lw((cs, z0), (rx, z0)); w2 = Lw((rx, z0), (cs, z0 + rz)); w3 = Lw((cs, z0 + rz), (cs, z0))
C = lambda *a: wsk.addConstraint(Sketcher.Constraint(*a))
C("Coincident", w1, 2, w2, 1); C("Coincident", w2, 2, w3, 1); C("Coincident", w3, 2, w1, 1)
C("Horizontal", w1); C("Vertical", w3)
dist_constraint(wsk, "DistanceX", -1, 1, w1, 1, F.u("Params.CavS / 2"), "x_wall")
dist_constraint(wsk, "DistanceX", -1, 1, w1, 2, F.u("Params.RampX_1"), "x_tip")
dist_constraint(wsk, "DistanceY", -1, 1, w1, 1, F.w("Params.CapZ_0 - 0.01"), "z_floor")
dist_constraint(wsk, "DistanceY", -1, 1, w3, 1, F.w("Params.CapZ_0 + Params.RampZ"), "z_rise")
wedge = pocket(cap, wsk, "Wedge", "2 * Params.RampHY", midplane=True)
mirrored(cap, wedge, "WedgeMirrored", "YZ_Plane")
sk = sketch(cap, "BossOutlines", "XY_Plane", "Params.BossZ_0")
circles4(sk, "Params.BossD", "Params.ScrewX", "Params.ScrewY")
pad(cap, sk, "Bosses", "Params.CapZ_0 + 0.01 - Params.BossZ_0")
sk = sketch(cap, "ShankHoleOutlines", "XY_Plane", "Params.CapTop")
circles4(sk, "Params.Shank", "Params.ScrewX", "Params.ScrewY")
pocket(cap, sk, "ShankHoles")
sk = sketch(cap, "HeadRecessOutlines", "XY_Plane", "Params.CapTop")
circles4(sk, "Params.Head", "Params.ScrewX", "Params.ScrewY")
rec = pocket(cap, sk, "HeadRecesses", "Params.CapTop - (Params.BossZ_0 + Params.HeadFloor)")
hr = vals["Head"] / 2
fillet(cap, rec, "RecessMouths", "Params.MouthR", lambda e: isinstance(e.Curve, Part.Circle) and abs(e.Curve.Radius - hr) < 0.01 and abs(e.BoundBox.ZMin - ztop) < 1e-6)
finish(cap, (0.93, 0.92, 0.88))

# ================= SHIM (between MDF and base) =================
shim = doc.addObject("PartDesign::Body", "Shim")
sk = sketch(shim, "ShimOutline", "XY_Plane", "-Params.Plate - Params.ShimT")
rrect(sk, "-Params.BaseL / 2", "Params.BaseL / 2", "-Params.BaseW / 2", "Params.BaseW / 2", "Params.CornerR")
pad(shim, sk, "ShimPlate", "Params.ShimT")
sk = sketch(shim, "ShimExitProfile", "XY_Plane", "-Params.Plate")
rect(sk, "Params.ExitX_0", "Params.BaseL / 2 + 1", "-Params.ExitHY", "Params.ExitHY")
pocket(shim, sk, "ShimExit")
sk = sketch(shim, "ShimHoleOutlines", "XY_Plane", "-Params.Plate")
circles4(sk, "Params.Shank", "Params.ScrewX", "Params.ScrewY")
pocket(shim, sk, "ShimScrewHoles")
finish(shim, (0.7, 0.7, 0.75)); hide(shim)

# ================= references (not printed) =================
metal = doc.addObject("PartDesign::Body", "CellMetal_ref")
sk = sketch(metal, "CellOutline", "XY_Plane", "Params.PlatH")
rrect(sk, "Params.CellX_0", "Params.CellX_1", "-Params.CellS / 2", "Params.CellS / 2", "Params.CellR")
pad(metal, sk, "CellBody", "Params.CellT")
sk = sketch(metal, "CellWindowOutline", "XY_Plane", "Params.FootZ")
rrect(sk, "Params.WinX_0", "Params.WinX_1", "-Params.WinHY", "Params.WinHY", "Params.WinR")
pocket(metal, sk, "CellWindow")
finish(metal, (0.75, 0.75, 0.78))
foot = doc.addObject("PartDesign::Body", "CellFoot_ref")
sk = sketch(foot, "FootBlockOutline", "XY_Plane", "Params.FootZ")
rect(sk, "-Params.FootBlkX / 2", "Params.FootBlkX / 2", "-Params.FootBlkY / 2", "Params.FootBlkY / 2")
pad(foot, sk, "FootBlock", "Params.FootBlkZ")
sk = sketch(foot, "ButtonOutline", "XY_Plane", "Params.FootZ + Params.FootBlkZ")
circle(sk, "0", "0", "Params.ButtonD")
pad(foot, sk, "FootButton", "Params.ButtonH")
finish(foot, (0.1, 0.1, 0.1))

check((base, cap, shim))
compare("LoadCellFoot", (("Base", "Base"), ("Cap", "Cap"), ("Shim", "Shim_1_0")))
doc.saveAs(os.path.join(CAD, "foot_param.FCStd"))
