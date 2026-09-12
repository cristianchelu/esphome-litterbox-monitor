import os, sys, math, importlib
import FreeCAD as App, Part, Sketcher
from FreeCAD import Vector as V

# HX711 shell as a PartDesign document: tray screwed to the MDF underside at the board centre, SparkFun HX711 on
# standoffs, feet cables enter under the floating wall corners. Frame as hx711.py: +Z toward the floor, MDF face at
# Z = -Plate. Run once to build the tree; after that the .FCStd is the design.

CAD = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'
if CAD not in sys.path: sys.path.insert(0, CAD)
import pdlib; importlib.reload(pdlib)
from pdlib import *

PARAMS = [
 ("Outline", None, None),
 ("TrayL",    72.0, "tray/cap outline, X (widened from 60 so the brain-ribbon exit clears the corner entries)"),
 ("TrayW",    80.0, "tray/cap outline, Y"),
 ("CornerR",  15.0, "outline corner radius"),
 ("Plate",     1.5, "tray plate thickness"),
 ("Wall",      1.5, "tray wall"),
 ("CompH",     2.5, "tallest thing on the HX711 board (chip, solder on the wire pads)"),
 ("Clr",       0.1, "print-to-print clearance"),
 ("CornerDiscD", 15.0, "plate kept as a quarter disc at each corner; the rest of the corner is open for the cable"),
 ("Screws", None, None),
 ("ScrewX",   22.5, "screw pattern half pitch, X"),
 ("ScrewY",   17.5, "screw pattern half pitch, Y"),
 ("Shank",     3.8, "screw shank hole"),
 ("Head",      7.5, "screw head recess"),
 ("HeadFloor", 1.3, "recess floor above the boss bottom"),
 ("MouthR",    1.0, "round-over on the recess mouths"),
 ("BossD",     9.5, "cap boss diameter"),
 ("Cap", None, None),
 ("CapT",      1.5, "cap plate thickness"),
 ("CapEdgeR",  1.0, "round-over on the cap plate's top edge"),
 ("LipT",      0.5, "cap rim thickness (drops into the rebate in the wall top)"),
 ("LipH",      2.0, "rebate depth"),
 ("HX711 board", None, None),
 ("PcbL",     22.86, "SparkFun HX711 breakout 0.9 in"),
 ("PcbW",     30.48, "1.2 in"),
 ("PcbT",      0.8, "as modelled in Fusion; SparkFun boards are usually 1.6 - measure!"),
 ("PcbHX",     8.89, "mounting holes 0.7 in apart"),
 ("PcbHY",    12.7, "1.0 in apart"),
 ("PcbHole",   3.3, "0.13 in"),
 ("StandD",    5.08, "standoff under each hole"),
 ("StandH",    1.0, "standoff height"),
 ("PinD",      2.8, "locating pin into the hole"),
 ("PinH",      0.8, "pin height above the standoff"),
 ("Catch posts", None, None),
 ("ClipT",     0.8, "post thickness"),
 ("ClipW",     3.0, "post width along the PCB edge"),
 ("ClipLip",   0.4, "45-degree catch over the PCB edge"),
 ("ClipOver",  1.0, "post continues this far above the catch's start"),
 ("ClipFootR", 0.8, "concave fillet at the post's root"),
 ("Cables", None, None),
 ("RibbonX",  14.2, "5-wire brain ribbon leaves under the +Y wall here (brain shell: RIB_XC)"),
 ("RibbonW",   8.0, "ribbon exit width"),
 ("RibbonIn",  7.0, "ribbon exit reaches this far in from the wall"),
 ("DupX",      9.0, "3-way Dupont housings lie flat at the +-Y ends between the bosses"),
 ("DupY",     19.8, ""),
 ("DupL",     14.0, "housing 7.62 x 2.54 x 14"),
 ("DupW",      7.62, ""),
 ("DupH",      2.54, ""),
 ("Derived", None, None),
 ("WallH",    "=round((StandH + PcbT + CompH + Clr) * 10) / 10", "wall top: just clears the board"),
 ("CapZ_0",   "=WallH", "cap plate underside sits on the wall tops"),
 ("CapTop",   "=CapZ_0 + CapT", "cap plate top"),
 ("CatchZ",   "=StandH + PcbT + Clr", "catch starts Clr above the PCB top"),
 ("CornerCX", "=TrayL / 2 - CornerR", "corner arc centre"),
 ("CornerCY", "=TrayW / 2 - CornerR", ""),
]
doc, ss = init("HX711ShellParam", PARAMS)
vals = pdlib.vals

# ================= TRAY =================
tray = doc.addObject("PartDesign::Body", "Tray")
sk = sketch(tray, "TrayOutline", "XY_Plane", "-Params.Plate")
rrect(sk, "-Params.TrayL / 2", "Params.TrayL / 2", "-Params.TrayW / 2", "Params.TrayW / 2", "Params.CornerR")
pad(tray, sk, "TrayBlock", "Params.Plate + Params.WallH")
sk = sketch(tray, "HollowOutline", "XY_Plane", "Params.WallH")
rrect(sk, "-Params.TrayL / 2 + Params.Wall", "Params.TrayL / 2 - Params.Wall", "-Params.TrayW / 2 + Params.Wall", "Params.TrayW / 2 - Params.Wall", "Params.CornerR - Params.Wall")
pocket(tray, sk, "Hollow", "Params.WallH")
# cable entry under each wall corner: the plate is cut away outside a quarter disc around the corner centre
sk = sketch(tray, "CornerBiteProfile", "XY_Plane", "0")
cx, cy, rd, hl, hw = vals["CornerCX"], vals["CornerCY"], vals["CornerDiscD"] / 2, vals["TrayL"] / 2, vals["TrayW"] / 2
L = lambda a, b: sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
l1 = L((cx + rd, cy), (hl, cy)); l2 = L((hl, cy), (hl, hw)); l3 = L((hl, hw), (cx, hw)); l4 = L((cx, hw), (cx, cy + rd))
arc = sk.addGeometry(Part.ArcOfCircle(Part.Circle(V(cx, cy, 0), V(0, 0, 1), rd), 0, math.pi / 2), False)
C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
C("Coincident", l1, 2, l2, 1); C("Coincident", l2, 2, l3, 1); C("Coincident", l3, 2, l4, 1); C("Coincident", l4, 2, arc, 2); C("Coincident", arc, 1, l1, 1)
C("Horizontal", l1); C("Vertical", l2); C("Horizontal", l3); C("Vertical", l4)
C("Horizontal", arc, 3, arc, 1); C("Vertical", arc, 3, arc, 2)      # a true quarter: ends level with / above the centre
i = C("Radius", arc, rd); sk.renameConstraint(i, "disc_r"); E(sk, ".Constraints.disc_r", "Params.CornerDiscD / 2")
dist_constraint(sk, "DistanceX", -1, 1, arc, 3, "Params.CornerCX", "centre_x")
dist_constraint(sk, "DistanceY", -1, 1, arc, 3, "Params.CornerCY", "centre_y")
dist_constraint(sk, "DistanceX", -1, 1, l2, 1, "Params.TrayL / 2", "outer_x")
dist_constraint(sk, "DistanceY", -1, 1, l3, 1, "Params.TrayW / 2", "outer_y")
bite = pocket(tray, sk, "CornerBite")
mirrored2(tray, bite, "CornerBites")
sk = sketch(tray, "RibbonExitProfile", "XY_Plane", "0")     # through the plate only; the wall above stays intact
rect(sk, "Params.RibbonX - Params.RibbonW / 2", "Params.RibbonX + Params.RibbonW / 2", "Params.TrayW / 2 - Params.Wall - Params.RibbonIn", "Params.TrayW / 2 + 1")
pocket(tray, sk, "RibbonExit")
sk = sketch(tray, "ScrewHoleOutlines", "XY_Plane", "0")
circles4(sk, "Params.Shank", "Params.ScrewX", "Params.ScrewY")
pocket(tray, sk, "ScrewHoles")
sk = sketch(tray, "StandoffOutlines", "XY_Plane", "0")
circles4(sk, "Params.StandD", "Params.PcbHX", "Params.PcbHY")
pad(tray, sk, "Standoffs", "Params.StandH")
sk = sketch(tray, "PinOutlines", "XY_Plane", "Params.StandH")
circles4(sk, "Params.PinD", "Params.PcbHX", "Params.PcbHY")
pad(tray, sk, "Pins", "Params.PinH")
# catch post beside the PCB's +X edge: 45-degree catch over the board (no flat overhang), concave fillet at the root
psk = sketch(tray, "CatchPostProfile", "XZ_Plane", "0")
F = Frame(psk, (0, 2))
xf = vals["PcbL"] / 2 + vals["Clr"]; xo = xf + vals["ClipT"]; z0 = vals["CatchZ"]; lip = vals["ClipLip"]; zt = z0 + vals["ClipOver"]; fr = vals["ClipFootR"]
L = lambda a, b: psk.addGeometry(Part.LineSegment(F.P(*a), F.P(*b)), False)
p1 = L((xf, 0), (xf, z0)); p2 = L((xf, z0), (xf - lip, z0 + lip)); p3 = L((xf - lip, z0 + lip), (xf, zt))
p4 = L((xf, zt), (xo, zt)); p5 = L((xo, zt), (xo, fr))
a0, a1 = (math.pi, 1.5 * math.pi) if not F.reflected else (0.5 * math.pi, math.pi)
root = psk.addGeometry(Part.ArcOfCircle(Part.Circle(F.P(xo + fr, fr), V(0, 0, 1), fr), a0, a1), False)
p6 = L((xo + fr, 0), (xf, 0))
C = lambda *a: psk.addConstraint(Sketcher.Constraint(*a))
C("Coincident", p1, 2, p2, 1); C("Coincident", p2, 2, p3, 1); C("Coincident", p3, 2, p4, 1); C("Coincident", p4, 2, p5, 1)
C("Tangent", p5, 2, root, 1); C("Tangent", root, 2, p6, 1); C("Coincident", p6, 2, p1, 1)
C("Vertical", p1); C("Horizontal", p4); C("Vertical", p5); C("Horizontal", p6)
C("PointOnObject", p1, 1, -1)                                        # the root sits on the plate top
C("Vertical", p1, 2, p4, 1)                                          # catch returns to the post face
i = C("Radius", root, fr); psk.renameConstraint(i, "root_r"); E(psk, ".Constraints.root_r", "Params.ClipFootR")
dist_constraint(psk, "DistanceX", -1, 1, p1, 1, F.u("Params.PcbL / 2 + Params.Clr"), "x_face")
dist_constraint(psk, "DistanceY", -1, 1, p1, 2, F.w("Params.CatchZ"), "z_catch")
dist_constraint(psk, "DistanceX", p2, 1, p2, 2, F.u("-Params.ClipLip"), "lip")
dist_constraint(psk, "DistanceY", p2, 1, p2, 2, F.w("Params.ClipLip"), "lip_rise")
dist_constraint(psk, "DistanceY", -1, 1, p4, 1, F.w("Params.CatchZ + Params.ClipOver"), "z_top")
dist_constraint(psk, "DistanceX", p1, 1, p4, 2, F.u("Params.ClipT"), "thickness")
post = pad(tray, psk, "CatchPost", "Params.ClipW", midplane=True)
mirrored(tray, post, "CatchPostMirrored", "YZ_Plane")
sk = sketch(tray, "RebateProfile", "XY_Plane", "Params.WallH")   # ring in the wall top for the cap's rim
rrect(sk, "-Params.TrayL / 2 + Params.Wall - Params.LipT - Params.Clr", "Params.TrayL / 2 - Params.Wall + Params.LipT + Params.Clr",
      "-Params.TrayW / 2 + Params.Wall - Params.LipT - Params.Clr", "Params.TrayW / 2 - Params.Wall + Params.LipT + Params.Clr", "Params.CornerR - Params.Wall + Params.LipT + Params.Clr", "_out")
rrect(sk, "-Params.TrayL / 2 + Params.Wall + 0.2", "Params.TrayL / 2 - Params.Wall - 0.2",
      "-Params.TrayW / 2 + Params.Wall + 0.2", "Params.TrayW / 2 - Params.Wall - 0.2", "Params.CornerR - Params.Wall - 0.2", "_in")
pocket(tray, sk, "Rebate", "Params.LipH")
finish(tray, (0.93, 0.92, 0.88))

# ================= CAP =================
cap = doc.addObject("PartDesign::Body", "Cap")
sk = sketch(cap, "CapOutline", "XY_Plane", "Params.CapZ_0")
rrect(sk, "-Params.TrayL / 2", "Params.TrayL / 2", "-Params.TrayW / 2", "Params.TrayW / 2", "Params.CornerR")
plate = pad(cap, sk, "CapPlate", "Params.CapT")
ztop = vals["CapTop"]
fillet(cap, plate, "CapEdge", "Params.CapEdgeR", lambda e: abs(e.BoundBox.ZMin - ztop) < 1e-6 and abs(e.BoundBox.ZMax - ztop) < 1e-6)
sk = sketch(cap, "RimProfile", "XY_Plane", "Params.CapZ_0")      # rim down into the tray's rebate
rrect(sk, "-Params.TrayL / 2 + Params.Wall - Params.LipT", "Params.TrayL / 2 - Params.Wall + Params.LipT",
      "-Params.TrayW / 2 + Params.Wall - Params.LipT", "Params.TrayW / 2 - Params.Wall + Params.LipT", "Params.CornerR - Params.Wall + Params.LipT", "_out")
rrect(sk, "-Params.TrayL / 2 + Params.Wall", "Params.TrayL / 2 - Params.Wall",
      "-Params.TrayW / 2 + Params.Wall", "Params.TrayW / 2 - Params.Wall", "Params.CornerR - Params.Wall", "_in")
pad(cap, sk, "Rim", "Params.LipH - Params.Clr", reversed_=True)
sk = sketch(cap, "BossOutlines", "XY_Plane", "Params.Clr")
circles4(sk, "Params.BossD", "Params.ScrewX", "Params.ScrewY")
pad(cap, sk, "Bosses", "Params.CapZ_0 + 0.01 - Params.Clr")
sk = sketch(cap, "ShankHoleOutlines", "XY_Plane", "Params.CapTop")
circles4(sk, "Params.Shank", "Params.ScrewX", "Params.ScrewY")
pocket(cap, sk, "ShankHoles")
sk = sketch(cap, "HeadRecessOutlines", "XY_Plane", "Params.CapTop")
circles4(sk, "Params.Head", "Params.ScrewX", "Params.ScrewY")
rec = pocket(cap, sk, "HeadRecesses", "Params.CapTop - (Params.Clr + Params.HeadFloor)")
hr = vals["Head"] / 2
fillet(cap, rec, "RecessMouths", "Params.MouthR", lambda e: isinstance(e.Curve, Part.Circle) and abs(e.Curve.Radius - hr) < 0.01 and abs(e.BoundBox.ZMin - ztop) < 1e-6)
finish(cap, (0.93, 0.92, 0.88))

# ================= references (not printed) =================
pcb = doc.addObject("PartDesign::Body", "HX711_ref")
sk = sketch(pcb, "PcbOutline", "XY_Plane", "Params.StandH")
rect(sk, "-Params.PcbL / 2", "Params.PcbL / 2", "-Params.PcbW / 2", "Params.PcbW / 2")
pad(pcb, sk, "PcbBoard", "Params.PcbT")
sk = sketch(pcb, "PcbHoleOutlines", "XY_Plane", "Params.StandH + Params.PcbT")
circles4(sk, "Params.PcbHole", "Params.PcbHX", "Params.PcbHY")
pocket(pcb, sk, "PcbHoles")
finish(pcb, (0.8, 0.1, 0.1))
dup = doc.addObject("PartDesign::Body", "Dupont_ref")
sk = sketch(dup, "DupontOutline", "XY_Plane", "Params.Clr")
rect(sk, "Params.DupX - Params.DupL / 2", "Params.DupX + Params.DupL / 2", "Params.DupY - Params.DupW / 2", "Params.DupY + Params.DupW / 2")
one = pad(dup, sk, "Dupont", "Params.DupH")
mirrored2(dup, one, "Duponts")
finish(dup, (0.85, 0.75, 0.1))

check((tray, cap))
compare("HX711Shell", (("Tray", "Tray"), ("Cap", "Cap")))
doc.saveAs(os.path.join(CAD, "hx711_param.FCStd"))
