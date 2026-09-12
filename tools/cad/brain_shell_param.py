import os, sys, math, importlib
import FreeCAD as App, Part, Sketcher
from FreeCAD import Vector as V

# Brain shell as a PartDesign document. Frame as brain_shell.py: X along the shelf edge (centred), +Y goes under the
# MDF, Z up, MDF top = 0. The white shell is one Body ("Shell": nose in front of the edge + tail under the board);
# "Top" and "Mid" start from that shell (through a binder) and each cuts away the other half, then adds its own glue-lip details.
# The black liners (Sleeve, TailSleeve, CapSleeve) and the white Cap are their own Bodies. Everything hangs off the
# Params sheet; the slope is a datum plane whose angle is a sheet formula.

CAD = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'
if CAD not in sys.path: sys.path.insert(0, CAD)
import pdlib; importlib.reload(pdlib)
from pdlib import *

PARAMS = [
 ("Shell", None, None),
 ("MdfT",     18.0, "KOMPLEMENT board thickness"),
 ("ShellW",   78.0, "width along the edge: the flat rear wall must span the ribbon slot and the USB notch"),
 ("ROut",     15.0, "plan-view corner radius at the nose"),
 ("RRear",    10.0, "tail corners: tighter, so the screw bosses fit inside the short tail's liner"),
 ("NTop",      8.0, "nose depth at the top (in front of the edge)"),
 ("NBot",     23.0, "nose depth at the bottom"),
 ("ZCorner", -16.0, "slope ends 2 mm above the MDF bottom plane; vertical skirt below"),
 ("Roof",      1.0, "tail roof against the MDF underside"),
 ("Wall",      1.2, "all shell walls"),
 ("Back",      1.2, "nose back wall (against the MDF edge)"),
 ("NoseRoof",  1.2, "nose roof"),
 ("PadWall",   0.9, "white wall left at the centre of the touch dish"),
 ("DiskD",    10.0, "touch-target dish diameter: a shallow spherical cap on the outer face"),
 ("EdgeR",     2.0, "round-over on the Top's convex outer edges"),
 ("BarWall",   0.8, "white wall left at the light bar"),
 ("Clr",       0.1, "minimum clearance between any two mating surfaces"),
 ("Gap",      "=Clr", "sleeve/base clearance"),
 ("LinerW",    0.9, "liner walls (two 0.42 perimeters of black is opaque)"),
 ("SWRoof",    0.8, "tail liner roof under the Mid roof, four layers"),
 ("SWPad",     0.4, "sleeve skin left in front of the touch pad"),
 ("CSW",       0.6, "cap sleeve: black plate lying on the cap, three layers"),
 ("CapT",      1.2, "cap plate"),
 ("LipH",      2.0, "glue lip: the Top's inner LipT drops into a rebate in the Mid skirt; same at the Mid/Cap seam"),
 ("LipT",      0.5, ""),
 ("ScrewX",   30.0, "two screw bosses on the flanks, inside the tail liner's rear corners"),
 ("ScrewY",    7.0, ""),
 ("BossR",     5.0, ""),
 ("ScrewHole", 3.9, "shank clearance"),
 ("ScrewHead", 7.6, "head recess in the cap"),
 ("ESP32-S3 SuperMini", None, None),
 ("PcbL",     23.5, "board 23.5 x 18 x 1.2, components UP so the WS2812 lights the nose cavity"),
 ("PcbW",     18.0, ""),
 ("PcbT",      1.2, ""),
 ("PcbX_0",  -23.2, "outer edge (unwired row); the board lives on the -X half"),
 ("PcbX_1",   -5.2, "inner edge (wired row)"),
 ("PinPitch",  2.54, "through-hole grid: 2 rows x 9"),
 ("PinInset",  1.27, "rows in from the long edges"),
 ("PinEnd",    1.59, "first pin from the USB end"),
 ("PinHole",   1.0, ""),
 ("LedY",     -3.5, "WS2812 between GPIO9/10, in front of the sleeve's roof edge: fixes the board's Y"),
 ("LedFromEdge", 2.5, ""),
 ("LedS",      2.0, ""),
 ("LedH",      1.0, ""),
 ("PegD",      0.7, "locating pegs into the pin-4 pads"),
 ("PegH",      1.0, ""),
 ("UsbHt",     3.11, "USB-C port shell 8.94 x 7.35 x 3.11, protrudes 1.5"),
 ("UsbW0",     8.94, ""),
 ("UsbClr",    0.3, "air between the port and the tail liner roof"),
 ("UsbHorn",   1.2, "shoulder each side of the port stadium that the cap's block fills"),
 ("Retention", None, None),
 ("Catch",     0.3, "snap catch depth; the post runs 0.1 past the catch's lower face"),
 ("StandW",    1.8, "standoffs on the pin-4 pads"),
 ("PostT",     0.8, "catch posts: slim, hanging from the liner roof"),
 ("PostW",     4.0, ""),
 ("FootR",     0.8, "concave fillet at the post's root"),
 ("Pin header", None, None),
 ("Pitch",     2.54, "four header pins printed into the liner for the HX711 ribbon"),
 ("PinSq",     0.64, ""),
 ("PinL",     11.5, ""),
 ("PinMate",   6.0, "exposed rear"),
 ("PinTail",   3.0, "solder front"),
 ("HoleW",     0.75, "press fit for the barbs; MEASURE after a test print"),
 ("HoleH",     0.85, ""),
 ("FhW",      10.16, "female housing on the ribbon"),
 ("FhT",       2.54, ""),
 ("FhL",      14.0, ""),
 ("Ribbon slot", None, None),
 ("RibHW",     6.0, "12 wide: a 4-pin Dupont housing has to pass through it"),
 ("RibDepth",  4.0, ""),
 ("Touch pad and light bar", None, None),
 ("PadL",     15.0, "TTP223B 15 x 11, pin strip at -X, lying on the slope"),
 ("PadW",     11.0, ""),
 ("PadPins",   3.5, ""),
 ("PadV_0",    1.7, "pin-free top edge just under the nose roof (v = distance down the slope)"),
 ("BarH",      3.0, "light bar, centred between the pad and the skirt corner"),
 ("BarHW",    20.0, ""),
 ("Derived", None, None),
 ("ZSplit",   "=-MdfT", "Top / Mid split"),
 ("SlopeAng", "=atan2(NBot - NTop; -ZCorner)", "slope from vertical"),
 ("SlopeLen", "=hypot(NBot - NTop; ZCorner)", ""),
 ("PcbXC",    "=(PcbX_0 + PcbX_1) / 2", "USB notch here, ribbon slot mirrored at -PcbXC"),
 ("PinXOut",  "=PcbX_0 + PinInset", ""),
 ("PinXIn",   "=PcbX_1 - PinInset", ""),
 ("PcbY_1",   "=LedY + PinEnd + 6.5 * PinPitch", "USB end"),
 ("PcbY_0",   "=PcbY_1 - PcbL", ""),
 ("LedX",     "=PcbX_1 - LedFromEdge", ""),
 ("PinY_4",   "=PcbY_1 - PinEnd - 3 * PinPitch", "pin 4 (standoffs and pegs)"),
 ("PinY_6",   "=PcbY_1 - PinEnd - 5 * PinPitch", "pin 6 (catch posts end here)"),
 ("RoofZ",    "=-MdfT - Roof", "Mid roof underside"),
 ("SRoofT",   "=RoofZ - Gap", "tail liner roof top"),
 ("SRoofB",   "=SRoofT - SWRoof", "tail liner roof underside: the ESP32 hangs from here"),
 ("UsbZT",    "=SRoofB - UsbClr", ""),
 ("PcbZT",    "=UsbZT - UsbHt", ""),
 ("PcbZB",    "=PcbZT - PcbT", ""),
 ("UsbZC",    "=(PcbZT + UsbZT) / 2", ""),
 ("UsbW",     "=UsbW0 + 0.5", "port opening"),
 ("UsbH",     "=UsbHt + 0.5", ""),
 ("PostBot",  "=PcbZB - 2 * Catch - 0.1", ""),
 ("PlateT",   "=PcbZB - 0.8", "cap sleeve top: pad-side passives + 0.1"),
 ("PlateB",   "=PlateT - CSW", ""),
 ("ZBot",     "=PlateB - Gap", "base underside / cap top"),
 ("CapBot",   "=ZBot - CapT", ""),
 ("TailT",    "=PcbY_1 + Clr + Wall", "tail depth: PCB end + clearance + rear wall"),
 ("RibXC",    "=-PcbXC", ""),
 ("RibX_0",   "=RibXC - RibHW", ""),
 ("RibX_1",   "=RibXC + RibHW", ""),
 ("PadX_0",   "=-(PadPins + (PadL - PadPins) / 2)", "puts the pad's circle on X = 0"),
 ("PadX_1",   "=PadX_0 + PadL", ""),
 ("PadV_1",   "=PadV_0 + PadW", ""),
 ("PadCircleV", "=(PadV_0 + PadV_1) / 2", ""),
 ("BarVC",    "=(PadV_1 + SlopeLen) / 2", ""),
 ("BarV_0",   "=BarVC - BarH / 2", ""),
 ("BarV_1",   "=BarVC + BarH / 2", ""),
 ("DishDepth", "=Wall - PadWall", ""),
 ("DishR",    "=(DiskD ^ 2 / 4 + DishDepth ^ 2) / (2 * DishDepth)", "sphere through the rim circle and the centre depth"),
 ("SleeveO",  "=Wall + Gap", "liner outer inset"),
 ("SleeveN",  "=SleeveO + LinerW", "liner inner inset"),
 ("SleeveQ",  "=SleeveN + Clr", "tongues and cap sleeve inset"),
 ("TailY_0",  "=-Back - Gap + Clr", "tail liner front face"),
 ("TongueL",   3.0, "tail liner tongues into the nose sleeve"),
 ("TongueT",   0.6, ""),
 ("ClipY_0",  "=PinY_6 - 0.8", "catch posts over pins 5-6"),
 ("ClipY_1",  "=ClipY_0 + PostW", ""),
 ("CarT",     "=PinL - PinMate - PinTail", "pin block thickness = the pin's barbed middle"),
 ("FhYR",     "=TailT - SleeveN - 3.5", "housing rear face: bend room to the liner's rear wall"),
 ("FhYF",     "=FhYR - FhL", ""),
 ("FhZ_0",    "=PlateT + Clr", "housing lies on the CapSleeve"),
 ("PinZC",    "=FhZ_0 + FhT / 2", "contact centre line"),
 ("CarYR",    "=FhYF - Clr", ""),
 ("CarYF",    "=CarYR - CarT", ""),
 ("CarZ_0",   "=PinZC - HoleH / 2 - 0.6", "0.6 of plastic under the holes"),
 ("CarX_0",   "=RibXC - FhW / 2 - 1", ""),
 ("CarX_1",   "=RibXC + FhW / 2 + 1", ""),
 ("BossTop",  "=SRoofB - Clr", ""),
 ("BarTop",   "=PcbZB - 0.5", "cap sleeve bar: room for the port's through-hole tabs"),
]
doc, ss = init("LitterboxBrainShellParam", PARAMS)
vals = pdlib.vals
def slope_plane(body):
    """the nose's sloped front face: local x = X, local y = v (down the slope), normal = inward"""
    dp = datum_plane(body, "SlopePlane")
    E(dp, "Placement.Base.x", "0"); E(dp, "Placement.Base.y", "-Params.NTop"); E(dp, "Placement.Base.z", "0")
    E(dp, "Placement.Rotation.Axis.x", "1"); E(dp, "Placement.Rotation.Axis.y", "0"); E(dp, "Placement.Rotation.Axis.z", "0")
    E(dp, "Placement.Rotation.Angle", "-(90 deg + Params.SlopeAng)")
    doc.recompute(); return dp
def slope_cut(body, sp, name, w):
    """pocket everything in front of the slope plane offset w inward"""
    sk = sketch(body, name + "Profile", sp, w, world=False)
    rect(sk, "-Params.ShellW / 2 - 10", "Params.ShellW / 2 + 10", "-40", "Params.SlopeLen + 40")
    return pocket(body, sk, name)
def nose_ring(sk, t_out, t_in, y_back, tag=""):
    """U-shaped ring in plan between the nose outline inset t_out and t_in, closed at y_back (glue lip / rebate)"""
    xo, yo, ro = ev("Params.ShellW / 2 - (%s)" % t_out), ev("-Params.NBot + (%s)" % t_out), ev("Params.ROut - (%s)" % t_out)
    xi, yi, ri = ev("Params.ShellW / 2 - (%s)" % t_in), ev("-Params.NBot + (%s)" % t_in), ev("Params.ROut - (%s)" % t_in)
    yb = ev(y_back)
    L = lambda a, b: sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
    A = lambda c, r, a1, a2: sk.addGeometry(Part.ArcOfCircle(Part.Circle(V(c[0], c[1], 0), V(0, 0, 1), r), math.radians(a1), math.radians(a2)), False)
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    l_lo = L((-xo, yb), (-xo, yo + ro)); a_lo = A((-xo + ro, yo + ro), ro, 180, 270); l_fo = L((-xo + ro, yo), (xo - ro, yo))
    a_ro = A((xo - ro, yo + ro), ro, 270, 360); l_ro = L((xo, yo + ro), (xo, yb)); l_br = L((xo, yb), (xi, yb))
    l_ri = L((xi, yb), (xi, yi + ri)); a_ri = A((xi - ri, yi + ri), ri, 270, 360); l_fi = L((xi - ri, yi), (-xi + ri, yi))
    a_li = A((-xi + ri, yi + ri), ri, 180, 270); l_li = L((-xi, yi + ri), (-xi, yb)); l_bl = L((-xi, yb), (-xo, yb))
    C("Tangent", l_lo, 2, a_lo, 1); C("Tangent", a_lo, 2, l_fo, 1); C("Tangent", l_fo, 2, a_ro, 1); C("Tangent", a_ro, 2, l_ro, 1)
    C("Tangent", l_ri, 2, a_ri, 2); C("Tangent", a_ri, 1, l_fi, 1); C("Tangent", l_fi, 2, a_li, 2); C("Tangent", a_li, 1, l_li, 1)
    C("Coincident", l_ro, 2, l_br, 1); C("Coincident", l_br, 2, l_ri, 1); C("Coincident", l_li, 2, l_bl, 1); C("Coincident", l_bl, 2, l_lo, 1)
    for g in (l_lo, l_ro, l_ri, l_li): C("Vertical", g)
    for g in (l_fo, l_br, l_fi, l_bl): C("Horizontal", g)
    C("Equal", a_lo, a_ro); C("Equal", a_ri, a_li)
    i = C("Radius", a_lo, ro); sk.renameConstraint(i, "r_out" + tag); E(sk, ".Constraints.r_out" + tag, "Params.ROut - (%s)" % t_out)
    i = C("Radius", a_ri, ri); sk.renameConstraint(i, "r_in" + tag); E(sk, ".Constraints.r_in" + tag, "Params.ROut - (%s)" % t_in)
    dist_constraint(sk, "DistanceX", -1, 1, l_lo, 1, "-(Params.ShellW / 2 - (%s))" % t_out, "x_out_l" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, l_ro, 2, "Params.ShellW / 2 - (%s)" % t_out, "x_out_r" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, l_fo, 1, "-Params.NBot + (%s)" % t_out, "y_front_out" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, l_ri, 1, "Params.ShellW / 2 - (%s)" % t_in, "x_in_r" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, l_li, 2, "-(Params.ShellW / 2 - (%s))" % t_in, "x_in_l" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, l_fi, 1, "-Params.NBot + (%s)" % t_in, "y_front_in" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, l_br, 1, y_back, "y_back" + tag)
    C("Horizontal", l_br, 1, l_bl, 1)
def port_profile(sk, F, x0, x1, zb, zj, xc, w, zc, r, tag=""):
    """the USB opening seen from the rear: a rectangle x0..x1 from zb up to zj, topped by the port stadium's upper half
    (width w centred on xc, straight sides from zj to zc, quarter arcs of radius r to a flat top)"""
    X0, X1, ZB, ZJ, XC, Wd, ZC, R = (ev(e) for e in (x0, x1, zb, zj, xc, w, zc, r))
    P = F.P
    L = lambda a, b: sk.addGeometry(Part.LineSegment(P(*a), P(*b)), False)
    def A(c, a1, a2):
        if F.reflected: a1, a2 = -a2, -a1
        return sk.addGeometry(Part.ArcOfCircle(Part.Circle(P(*c), V(0, 0, 1), R), math.radians(a1), math.radians(a2)), False)
    s, e = (2, 1) if F.reflected else (1, 2)
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    vertical = abs(ZC - ZJ) > 1e-9
    bot = L((X0, ZB), (X1, ZB)); rgt = L((X1, ZB), (X1, ZJ)); sh_r = L((X1, ZJ), (XC + Wd/2, ZJ))
    up_r = L((XC + Wd/2, ZJ), (XC + Wd/2, ZC)) if vertical else None
    a_r = A((XC + Wd/2 - R, ZC), 0, 90); top = L((XC + Wd/2 - R, ZC + R), (XC - Wd/2 + R, ZC + R)); a_l = A((XC - Wd/2 + R, ZC), 90, 180)
    up_l = L((XC - Wd/2, ZC), (XC - Wd/2, ZJ)) if vertical else None
    sh_l = L((XC - Wd/2, ZJ), (X0, ZJ)); lft = L((X0, ZJ), (X0, ZB))
    C("Coincident", bot, 2, rgt, 1); C("Coincident", rgt, 2, sh_r, 1)
    if vertical:
        C("Coincident", sh_r, 2, up_r, 1); C("Tangent", up_r, 2, a_r, s); C("Vertical", up_r)
        C("Tangent", a_l, e, up_l, 1); C("Coincident", up_l, 2, sh_l, 1); C("Vertical", up_l)
        C("Horizontal", sh_r, 1, sh_l, 2)                                  # both shoulders at the join height
    else:
        C("Coincident", sh_r, 2, a_r, s); C("Coincident", a_l, e, sh_l, 1)
    C("Tangent", a_r, e, top, 1); C("Tangent", top, 2, a_l, s)
    C("Coincident", sh_l, 2, lft, 1); C("Coincident", lft, 2, bot, 1)
    C("Horizontal", bot); C("Vertical", rgt); C("Horizontal", sh_r); C("Horizontal", top); C("Horizontal", sh_l); C("Vertical", lft)
    C("Equal", a_r, a_l)
    i = C("Radius", a_r, R); sk.renameConstraint(i, "r" + tag); E(sk, ".Constraints.r" + tag, r)
    if not vertical:
        C("Horizontal", a_r, 3, a_r, s); C("Horizontal", a_l, 3, a_l, e)    # arcs start level with their centres
    dist_constraint(sk, "DistanceX", -1, 1, bot, 1, F.u(x0), "x0" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, bot, 2, F.u(x1), "x1" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, bot, 1, F.w(zb), "z_bot" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, sh_r, 1, F.w(zj), "z_join" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, sh_r, 2, F.u("(%s) + (%s) / 2" % (xc, w)), "x_port_r" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, sh_l, 1, F.u("(%s) - (%s) / 2" % (xc, w)), "x_port_l" + tag)
    if vertical: dist_constraint(sk, "DistanceY", -1, 1, up_r, 2, F.w(zc), "z_port" + tag)

# ================= SHELL (white, nose + tail, before the Top/Mid split) =================
shell = doc.addObject("PartDesign::Body", "Shell")
sk = sketch(shell, "NoseOutline", "XY_Plane", "Params.ZBot")
rrect_c(sk, "-Params.ShellW / 2", "Params.ShellW / 2", "-Params.NBot", "0", "Params.ROut", None)
pad(shell, sk, "NoseBlock", "-Params.ZBot")
sp_shell = slope_plane(shell)
slope = slope_cut(shell, sp_shell, "Slope", "0")
# the nose cavity is a tool body (outline inset Wall, bounded by the slope offset Wall inward), cut from the shell.
# (A Thickness feature makes the same cavity, but its element naming did not survive nose edits: the Top's fillets lost
# their edges. Boolean naming does.)
cavtool = doc.addObject("PartDesign::Body", "NoseCavityTool")
sk = sketch(cavtool, "NoseCavityOutline", "XY_Plane", "Params.ZBot - 5")
rrect_c(sk, "-Params.ShellW / 2 + Params.Wall", "Params.ShellW / 2 - Params.Wall", "-Params.NBot + Params.Wall", "-Params.Back", "Params.ROut - Params.Wall", None)
pad(cavtool, sk, "NoseCavityBlock", "-Params.NoseRoof - (Params.ZBot - 5)")
slope_cut(cavtool, slope_plane(cavtool), "NoseCavitySlope", "Params.Wall")
finish(cavtool, (0.5, 0.5, 0.5)); hide(cavtool)
nose_shell = boolean(shell, "NoseCavity", "Cut", [cavtool])
nose_cav = cavtool.Shape                                           # kept for the Top's edge selection below
sk = sketch(shell, "TailOutline", "XY_Plane", "Params.ZBot")
rrect_c(sk, "-Params.ShellW / 2", "Params.ShellW / 2", "0", "Params.TailT", None, "Params.RRear")
pad(shell, sk, "TailBlock", "-Params.MdfT - Params.ZBot")
sk = sketch(shell, "TailCavityOutline", "XY_Plane", "Params.RoofZ")
rrect_c(sk, "-Params.ShellW / 2 + Params.Wall", "Params.ShellW / 2 - Params.Wall", "-Params.Back - 1", "Params.TailT - Params.Wall", None, "Params.RRear - Params.Wall")
pocket(shell, sk, "TailCavity")
sub_sphere(shell, "TouchDish", "Params.DishR", sp_shell, "0", "Params.PadCircleV", "-(Params.DishR - Params.DishDepth)")
sk = sketch(shell, "LightBarProfile", sp_shell, "Params.BarWall", world=False)
stadium(sk, "-Params.BarHW - 0.3", "Params.BarHW + 0.3", "Params.BarV_0 - 0.3", "Params.BarV_1 + 0.3")
pocket(shell, sk, "LightBarThinning", "Params.Wall + 0.6 - Params.BarWall", reversed_=True)
sk = sketch(shell, "PortProfile", "XZ_Plane", "Params.TailT + 1")
F = Frame(sk, (0, 2))
port_profile(sk, F, "Params.PcbXC - Params.UsbW / 2 - Params.UsbHorn", "Params.PcbXC + Params.UsbW / 2 + Params.UsbHorn", "Params.ZBot - 1", "Params.UsbZC", "Params.PcbXC", "Params.UsbW", "Params.UsbZC", "Params.UsbH / 2")
pocket(shell, sk, "PortOpening", "Params.TailT + 1 - (Params.PcbY_1 - 1)", reversed_=(normal_sign(sk) < 0))
sk = sketch(shell, "RibbonSlotProfile", "XY_Plane", "-Params.MdfT + 0.1")
rect(sk, "Params.RibX_0", "Params.RibX_1", "Params.TailT - Params.Wall - Params.RibDepth", "Params.TailT + 1")
pocket(shell, sk, "RibbonSlot", "Params.Roof + 0.1")
sk = sketch(shell, "ScrewHoleOutlines", "XY_Plane", "-Params.MdfT")
circles2(sk, "Params.ScrewHole", "Params.ScrewX", "Params.ScrewY")
pocket(shell, sk, "ScrewHoles")
finish(shell, (0.93, 0.92, 0.88)); hide(shell)

# ================= TOP (nose above the split) =================
def outer_edges(sh, cav, min_deg=10.0):
    """convex outer edges above the split: not on the bottom or the rear face, clear of the cavity, with a real
    dihedral angle (skips tangent seams and the touch dish's rim)"""
    out = []
    zs = vals["ZSplit"]
    for i, e in enumerate(sh.Edges):
        bb = e.BoundBox
        if bb.ZMax < zs + 0.5 or bb.YMin > -1e-6: continue
        pm = e.valueAt(e.FirstParameter + 0.5 * (e.LastParameter - e.FirstParameter))
        if cav.distToShape(Part.Vertex(pm))[0] < 0.6: continue
        faces = [f for f in sh.Faces if any(fe.isSame(e) for fe in f.Edges)]
        if len(faces) != 2: continue
        ns = []
        for f in faces:
            u, v = f.Surface.parameter(pm); ns.append(f.normalAt(u, v))
        a = math.degrees(ns[0].getAngle(ns[1]))
        if min(a, 180 - a) < min_deg: continue
        out.append(i)
    return out
top = doc.addObject("PartDesign::Body", "Top")
derive(top, shell, "ShellForTop")
sk = sketch(top, "TopSplit", "XY_Plane", "Params.ZSplit")
rect(sk, "-Params.ShellW / 2 - 1", "Params.ShellW / 2 + 1", "-Params.NBot - 1", "Params.TailT + 1")
common = pocket(top, sk, "BelowSplit")                       # everything under the split goes to the Mid
ntop = vals["NTop"]
front = [i for i in outer_edges(common.Shape, nose_cav) if abs(common.Shape.Edges[i].BoundBox.ZMax) < 1e-6
         and abs(common.Shape.Edges[i].BoundBox.YMax + ntop) < 1e-6 and abs(common.Shape.Edges[i].BoundBox.YMin + ntop) < 1e-6]
# two passes, as in the script: OCC refuses the front edge in the same call as any other (the vertex where side plane,
# corner cylinder, top and slope meet), so it goes first and the rest - including the new fillet's end edges - blend in
f1 = fillet(top, common, "TopFrontEdge", "Params.EdgeR", front)
f2 = fillet(top, f1, "TopEdges", "Params.EdgeR", outer_edges(f1.Shape, nose_cav))
sk = sketch(top, "LipProfile", "XY_Plane", "Params.ZSplit")
nose_ring(sk, "Params.Wall - Params.LipT", "Params.Wall", "-Params.Back")
pad(top, sk, "Lip", "Params.LipH - Params.Clr", reversed_=True)
finish(top, (0.93, 0.92, 0.88))

# ================= MID (skirt + tail below the split) =================
mid = doc.addObject("PartDesign::Body", "Mid")
derive(mid, shell, "ShellForMid")
sk = sketch(mid, "MidSplit", "XY_Plane", "Params.ZSplit")
rect(sk, "-Params.ShellW / 2 - 1", "Params.ShellW / 2 + 1", "-Params.NBot - 1", "Params.TailT + 1")
pocket(mid, sk, "AboveSplit", reversed_=True)
sk = sketch(mid, "RebateProfile", "XY_Plane", "Params.ZSplit")
nose_ring(sk, "Params.Wall - Params.LipT - Params.Clr", "Params.Wall + 0.2", "-Params.Back")
pocket(mid, sk, "Rebate", "Params.LipH")
sk = sketch(mid, "CapRebateProfile", "XY_Plane", "Params.ZBot")
for t, tag in (("Params.Wall - Params.LipT - Params.Clr", "_out"), ("Params.Wall + 0.2", "_in")):
    rrect_c(sk, "-Params.ShellW / 2 + (%s)" % t, "Params.ShellW / 2 - (%s)" % t, "-Params.NBot + (%s)" % t, "Params.TailT - (%s)" % t, "Params.ROut - (%s)" % t, "Params.RRear - (%s)" % t, tag)
pocket(mid, sk, "CapRebate", "Params.LipH", reversed_=True)
finish(mid, (0.88, 0.87, 0.83))


# ================= SLEEVE (black nose liner) =================
sleeve = doc.addObject("PartDesign::Body", "Sleeve")
sk = sketch(sleeve, "SleeveOutline", "XY_Plane", "Params.ZBot + Params.Clr")
rrect_c(sk, "-Params.ShellW / 2 + Params.SleeveO", "Params.ShellW / 2 - Params.SleeveO", "-Params.NBot + Params.SleeveO", "-Params.Back - Params.Gap", "Params.ROut - Params.SleeveO", None)
pad(sleeve, sk, "SleeveBlock", "-Params.NoseRoof - Params.Gap - (Params.ZBot + Params.Clr)")
sp_sleeve = slope_plane(sleeve)
sl = slope_cut(sleeve, sp_sleeve, "SleeveSlope", "Params.SleeveO")
zs0 = vals["ZBot"] + vals["Clr"]
thickness(sleeve, sl, "SleeveShell", "Params.LinerW", lambda f: abs(f.BoundBox.ZMin - zs0) < 1e-6 and abs(f.BoundBox.ZMax - zs0) < 1e-6)
sk = sketch(sleeve, "PadRecessProfile", sp_sleeve, "Params.Wall + Params.Gap + Params.SWPad", world=False)   # inside; the skin stays
rect(sk, "Params.PadX_0 - Params.Clr", "Params.PadX_1 + Params.Clr", "Params.PadV_0 - Params.Clr", "Params.PadV_1 + Params.Clr")
pocket(sleeve, sk, "PadRecess", "4 - (Params.Wall + Params.Gap + Params.SWPad)", reversed_=True)
sk = sketch(sleeve, "BarSlotProfile", sp_sleeve, "1", world=False)
stadium(sk, "-Params.BarHW", "Params.BarHW", "Params.BarV_0", "Params.BarV_1")
pocket(sleeve, sk, "BarSlot", "3", reversed_=True)
sk = sketch(sleeve, "BackOpeningProfile", "XY_Plane", "Params.SRoofT + Params.Clr")   # back wall open below the tail liner's roof
rect(sk, "-Params.ShellW / 2 + Params.SleeveN", "Params.ShellW / 2 - Params.SleeveN", "-Params.Back - Params.Gap - Params.LinerW - 1", "-Params.Back - Params.Gap + 1")
pocket(sleeve, sk, "BackOpening")
finish(sleeve, (0.12, 0.12, 0.12))

# ================= TAIL SLEEVE (black tail liner: open-bottom box, roof under the Mid roof, all the PCB retention) ====
tail = doc.addObject("PartDesign::Body", "TailSleeve")
sk = sketch(tail, "TailLinerOutline", "XY_Plane", "Params.ZBot + Params.Clr")
rrect_c(sk, "-Params.ShellW / 2 + Params.SleeveO", "Params.ShellW / 2 - Params.SleeveO", "Params.TailY_0", "Params.TailT - Params.SleeveO", None, "Params.RRear - Params.SleeveO")
pad(tail, sk, "TailLinerBlock", "Params.SRoofT - (Params.ZBot + Params.Clr)")
sk = sketch(tail, "TailLinerCavityOutline", "XY_Plane", "Params.SRoofB")
rrect_c(sk, "-Params.ShellW / 2 + Params.SleeveN", "Params.ShellW / 2 - Params.SleeveN", "Params.TailY_0 - 1", "Params.TailT - Params.SleeveN", None, "Params.RRear - Params.SleeveN")
pocket(tail, sk, "TailLinerCavity")
# lapped joint to the nose sleeve: the roof runs on under its back wall, thin tongues continue the side walls inside it
sk = sketch(tail, "RoofTongueProfile", "XY_Plane", "Params.SRoofB")
rect(sk, "-Params.ShellW / 2 + Params.SleeveQ", "Params.ShellW / 2 - Params.SleeveQ", "-Params.Back - Params.Gap - Params.LinerW - Params.Clr", "Params.TailY_0")
pad(tail, sk, "RoofTongue", "Params.SWRoof")
sk = sketch(tail, "SideTongueProfiles", "XY_Plane", "Params.PlateT + Params.Clr")
rect(sk, "-Params.ShellW / 2 + Params.SleeveQ", "-Params.ShellW / 2 + Params.SleeveQ + Params.TongueT", "Params.TailY_0 - Params.TongueL", "Params.TailY_0", "_l")
rect(sk, "Params.ShellW / 2 - Params.SleeveQ - Params.TongueT", "Params.ShellW / 2 - Params.SleeveQ", "Params.TailY_0 - Params.TongueL", "Params.TailY_0", "_r")
pad(tail, sk, "SideTongues", "Params.SRoofT - (Params.PlateT + Params.Clr)")
# rear wall: slot for the board (open bottom, the board comes up from below) with the port U above it
sk = sketch(tail, "RearOpeningProfile", "XZ_Plane", "Params.TailT + 1")
F = Frame(sk, (0, 2))
port_profile(sk, F, "Params.PcbX_0 - Params.Clr", "Params.PcbX_1 + Params.Clr", "Params.ZBot - 1", "Params.PcbZT + Params.Clr", "Params.PcbXC", "Params.UsbW", "Params.UsbZC", "Params.UsbH / 2")
pocket(tail, sk, "RearOpening", "Params.SleeveN + 2", reversed_=(normal_sign(sk) < 0))
sk = sketch(tail, "LinerRibbonSlotProfile", "XY_Plane", "Params.SRoofT + 0.1")
rect(sk, "Params.RibX_0", "Params.RibX_1", "Params.TailT - Params.Wall - Params.RibDepth", "Params.TailT + 1")
pocket(tail, sk, "LinerRibbonSlot", "Params.SWRoof + 0.2")
sk = sketch(tail, "LinerScrewOutlines", "XY_Plane", "Params.SRoofT")
circles2(sk, "Params.ScrewHole", "Params.ScrewX", "Params.ScrewY")
pocket(tail, sk, "LinerScrewClearance")
# PCB retention, all on the liner roof: standoff + peg on the pin-4 pad, a snap post over pins 5-6, one side modelled
# and mirrored about the board's centre line; a pad rests on the port shell
sk = sketch(tail, "StandoffProfile", "XY_Plane", "Params.SRoofB")
rect(sk, "Params.PcbX_0 - 1", "Params.PcbX_0 + Params.StandW", "Params.PinY_4 - Params.StandW / 2", "Params.PinY_4 + Params.StandW / 2")
standoff = pad(tail, sk, "Standoff", "Params.SRoofB - Params.PcbZT", reversed_=True)
sk = sketch(tail, "PegProfile", "XY_Plane", "Params.PcbZT + 0.5")
circle(sk, "Params.PinXOut", "Params.PinY_4", "Params.PegD")
peg = pad(tail, sk, "Peg", "Params.PegH + 0.5", reversed_=True)
psk = sketch(tail, "CatchPostProfile", "XZ_Plane", "(Params.ClipY_0 + Params.ClipY_1) / 2")
F = Frame(psk, (0, 2))
xf = vals["PcbX_0"] - vals["Clr"]; xo = xf - vals["PostT"]; fr = vals["FootR"]; zr = vals["SRoofB"]; zb = vals["PostBot"]; zp = vals["PcbZB"]; ct = vals["Catch"]
L = lambda a, b: psk.addGeometry(Part.LineSegment(F.P(*a), F.P(*b)), False)
l1 = L((xo, zr - fr), (xo, zb)); l2 = L((xo, zb), (xf, zb)); l3 = L((xf, zb), (xf + ct, zp - ct)); l4 = L((xf + ct, zp - ct), (xf, zp))
l5 = L((xf, zp), (xf, zr)); l6 = L((xf, zr), (xo - fr, zr))
a0, a1 = (0, 90) if not F.reflected else (-90, 0)
root = psk.addGeometry(Part.ArcOfCircle(Part.Circle(F.P(xo - fr, zr - fr), V(0, 0, 1), fr), math.radians(a0), math.radians(a1)), False)
rs, re_ = (1, 2) if not F.reflected else (2, 1)
C = lambda *a: psk.addConstraint(Sketcher.Constraint(*a))
C("Tangent", l1, 1, root, rs); C("Tangent", root, re_, l6, 2)
C("Coincident", l1, 2, l2, 1); C("Coincident", l2, 2, l3, 1); C("Coincident", l3, 2, l4, 1); C("Coincident", l4, 2, l5, 1); C("Coincident", l5, 2, l6, 1)
C("Vertical", l1); C("Horizontal", l2); C("Vertical", l5); C("Horizontal", l6)
C("Vertical", l2, 2, l5, 1)                                          # catch bottom under the post face
i = C("Radius", root, fr); psk.renameConstraint(i, "root_r"); E(psk, ".Constraints.root_r", "Params.FootR")
dist_constraint(psk, "DistanceX", -1, 1, l5, 1, F.u("Params.PcbX_0 - Params.Clr"), "x_face")
dist_constraint(psk, "DistanceY", -1, 1, l5, 1, F.w("Params.PcbZB"), "z_pcb")
dist_constraint(psk, "DistanceX", l4, 2, l4, 1, F.u("Params.Catch"), "catch")
dist_constraint(psk, "DistanceY", l4, 2, l4, 1, F.w("-Params.Catch"), "catch_drop")
dist_constraint(psk, "DistanceY", -1, 1, l2, 1, F.w("Params.PostBot"), "z_bottom")
dist_constraint(psk, "DistanceY", -1, 1, l6, 1, F.w("Params.SRoofB"), "z_roof")
dist_constraint(psk, "DistanceX", l5, 1, l1, 1, F.u("-Params.PostT"), "thickness")
post = pad(tail, psk, "CatchPost", "Params.PostW", midplane=True)
pcb_mid = datum_plane(tail, "PcbMidPlane", "YZ_Plane", "Params.PcbXC")
mirrored_about(tail, [standoff, peg, post], "RetentionMirrored", pcb_mid)
sk = sketch(tail, "PortRestProfile", "XY_Plane", "Params.SRoofB")
rect(sk, "Params.PcbXC - 2.5", "Params.PcbXC + 2.5", "Params.PcbY_1 - 6", "Params.PcbY_1 - 1")
pad(tail, sk, "PortRest", "Params.SRoofB - (Params.UsbZT + Params.Clr)", reversed_=True)
# pin header block for the HX711 ribbon, hanging from the roof: four holes at 2.54 pitch for bare header pins
sk = sketch(tail, "PinBlockProfile", "XY_Plane", "Params.SRoofB")
rect(sk, "Params.CarX_0", "Params.CarX_1", "Params.CarYF", "Params.CarYR")
pad(tail, sk, "PinBlock", "Params.SRoofB - Params.CarZ_0", reversed_=True)
sk = sketch(tail, "PinHoleProfiles", "XZ_Plane", "Params.CarYR + 1")
F = Frame(sk, (0, 2))
for k in range(4):
    xc = "Params.RibXC + (%d - 1.5) * Params.Pitch" % k
    rect(sk, F.u("%s - Params.HoleW / 2" % xc), F.u("%s + Params.HoleW / 2" % xc), F.w("Params.PinZC - Params.HoleH / 2"), F.w("Params.PinZC + Params.HoleH / 2"), "_%d" % (k + 1))
pocket(tail, sk, "PinHoles", "Params.CarT + 2", reversed_=(normal_sign(sk) < 0))
sk = sketch(tail, "RoofLobeProfile", "XY_Plane", "Params.SRoofB")      # roof over the block, so it sits on the bed
rect(sk, "Params.CarX_0", "Params.CarX_1", "Params.CarYF", "-Params.Back - Params.Gap - Params.LinerW - Params.Clr")
pad(tail, sk, "RoofLobe", "Params.SWRoof")
finish(tail, (0.15, 0.15, 0.15))

# ================= CAP SLEEVE (black plate on the cap) =================
cs = doc.addObject("PartDesign::Body", "CapSleeve")
sk = sketch(cs, "CapSleeveOutline", "XY_Plane", "Params.PlateB")
rrect_c(sk, "-Params.ShellW / 2 + Params.SleeveQ", "Params.ShellW / 2 - Params.SleeveQ", "-Params.NBot + Params.SleeveQ", "Params.TailT - Params.SleeveQ", "Params.ROut - Params.SleeveQ", "Params.RRear - Params.SleeveQ")
pad(cs, sk, "CapSleevePlate", "Params.CSW")
sk = sketch(cs, "BossClearanceOutlines", "XY_Plane", "Params.PlateT")
circles2(sk, "2 * (Params.BossR + Params.Clr)", "Params.ScrewX", "Params.ScrewY")
pocket(cs, sk, "BossClearance")
sk = sketch(cs, "AntennaRestProfile", "XY_Plane", "Params.PlateT")             # the board's antenna end rests here
rect(sk, "Params.PcbX_0 + 3", "Params.PcbX_1 - 3", "Params.PcbY_0", "Params.PcbY_0 + 1.5")
pad(cs, sk, "AntennaRest", "Params.PcbZB - Params.Clr - Params.PlateT")
sk = sketch(cs, "SlotBarProfile", "XY_Plane", "Params.PlateB")                 # fills the tail liner's board slot below the board
rect(sk, "Params.PcbX_0", "Params.PcbX_1", "Params.TailT - Params.SleeveQ - 0.2", "Params.TailT - Params.SleeveO")
pad(cs, sk, "SlotBar", "Params.BarTop - Params.PlateB")
finish(cs, (0.18, 0.18, 0.18))

# ================= CAP (white) =================
cap = doc.addObject("PartDesign::Body", "Cap")
sk = sketch(cap, "CapOutline", "XY_Plane", "Params.CapBot")
rrect_c(sk, "-Params.ShellW / 2", "Params.ShellW / 2", "-Params.NBot", "Params.TailT", "Params.ROut", "Params.RRear")
pad(cap, sk, "CapPlate", "Params.CapT")
sk = sketch(cap, "BossOutlines", "XY_Plane", "Params.ZBot")
circles2(sk, "2 * Params.BossR", "Params.ScrewX", "Params.ScrewY")
pad(cap, sk, "Bosses", "Params.BossTop - Params.ZBot")
sk = sketch(cap, "CapScrewOutlines", "XY_Plane", "Params.BossTop")
circles2(sk, "Params.ScrewHole", "Params.ScrewX", "Params.ScrewY")
pocket(cap, sk, "CapScrewHoles")
sk = sketch(cap, "HeadRecessOutlines", "XY_Plane", "Params.CapBot")            # head recessed to a CapT-thick web under the roof
circles2(sk, "Params.ScrewHead", "Params.ScrewX", "Params.ScrewY")
pocket(cap, sk, "HeadRecesses", "Params.BossTop - Params.CapT - Params.CapBot", reversed_=True)
sk = sketch(cap, "PortBlockProfile", "XY_Plane", "Params.ZBot")                # lower half of the port opening lives on the cap
rect(sk, "Params.PcbXC - Params.UsbW / 2 - Params.UsbHorn + Params.Clr", "Params.PcbXC + Params.UsbW / 2 + Params.UsbHorn - Params.Clr", "Params.TailT - Params.Wall", "Params.TailT")
pad(cap, sk, "PortBlock", "Params.UsbZC - Params.Clr - Params.ZBot")
sk = sketch(cap, "RimProfile", "XY_Plane", "Params.ZBot")                      # rim into the Mid's rebate
for t, tag in (("Params.Wall - Params.LipT", "_out"), ("Params.Wall", "_in")):
    rrect_c(sk, "-Params.ShellW / 2 + (%s)" % t, "Params.ShellW / 2 - (%s)" % t, "-Params.NBot + (%s)" % t, "Params.TailT - (%s)" % t, "Params.ROut - (%s)" % t, "Params.RRear - (%s)" % t, tag)
pad(cap, sk, "Rim", "Params.LipH - Params.Clr")
sk = sketch(cap, "PortStadiumProfile", "XZ_Plane", "Params.TailT + 1")        # neither block nor rim may close the port
F = Frame(sk, (0, 2))
stadium(sk, "Params.PcbXC - Params.UsbW / 2", "Params.PcbXC + Params.UsbW / 2", "Params.UsbZC - Params.UsbH / 2", "Params.UsbZC + Params.UsbH / 2", P=F.P)
pocket(cap, sk, "PortStadium", "Params.Wall + 2", reversed_=(normal_sign(sk) < 0))
finish(cap, (0.93, 0.92, 0.88))

# ================= references (not printed) =================
esp = doc.addObject("PartDesign::Body", "ESP32_ref")
sk = sketch(esp, "PcbOutline", "XY_Plane", "Params.PcbZB")
rect(sk, "Params.PcbX_0", "Params.PcbX_1", "Params.PcbY_0", "Params.PcbY_1")
pad(esp, sk, "Pcb", "Params.PcbT")
sk = sketch(esp, "PinHoleOutlines", "XY_Plane", "Params.PcbZT")
for row, xr in (("out", "Params.PinXOut"), ("in", "Params.PinXIn")):
    for k in range(9): circle(sk, xr, "Params.PcbY_1 - Params.PinEnd - %d * Params.PinPitch" % k, "Params.PinHole", "_%s%d" % (row, k + 1))
pocket(esp, sk, "PcbPinHoles")
sk = sketch(esp, "UsbShellProfile", "XZ_Plane", "Params.PcbY_1 + 1.5")
F = Frame(sk, (0, 2))
stadium(sk, "Params.PcbXC - Params.UsbW0 / 2", "Params.PcbXC + Params.UsbW0 / 2", "Params.UsbZC - Params.UsbHt / 2", "Params.UsbZC + Params.UsbHt / 2", P=F.P)
pad(esp, sk, "UsbShell", "7.35", reversed_=(normal_sign(sk) > 0))
finish(esp, (0.1, 0.35, 0.1))
led = doc.addObject("PartDesign::Body", "LED_ref")
sk = sketch(led, "LedOutline", "XY_Plane", "Params.PcbZT")
rect(sk, "Params.LedX - Params.LedS / 2", "Params.LedX + Params.LedS / 2", "Params.LedY - Params.LedS / 2", "Params.LedY + Params.LedS / 2")
pad(led, sk, "Led", "Params.LedH"); finish(led, (0.2, 0.9, 0.3))
plug = doc.addObject("PartDesign::Body", "USBplug_ref")
sk = sketch(plug, "PlugProfile", "XZ_Plane", "Params.PcbY_1 + 1.5")
F = Frame(sk, (0, 2))
rect(sk, F.u("Params.PcbXC - 6"), F.u("Params.PcbXC + 6"), F.w("Params.UsbZC - 3.25"), F.w("Params.UsbZC + 3.25"))
pad(plug, sk, "Plug", "20", reversed_=(normal_sign(sk) < 0)); finish(plug, (0.3, 0.3, 0.3))
if GUI: plug.Tip.ViewObject.Transparency = 60
padb = doc.addObject("PartDesign::Body", "TTP223_ref")
sp_pad = slope_plane(padb)
sk = sketch(padb, "TouchPadOutline", sp_pad, "Params.Wall + Params.Gap + Params.SWPad", world=False)   # taped into the sleeve recess
rect(sk, "Params.PadX_0", "Params.PadX_1", "Params.PadV_0", "Params.PadV_1")
pad(padb, sk, "TouchPad", "1.2"); finish(padb, (0.8, 0.1, 0.1))
pins = doc.addObject("PartDesign::Body", "Pins_ref")
sk = sketch(pins, "PinProfiles", "XZ_Plane", "Params.CarYF - Params.PinTail")
F = Frame(sk, (0, 2))
for k in range(4):
    xc = "Params.RibXC + (%d - 1.5) * Params.Pitch" % k
    rect(sk, F.u("%s - Params.PinSq / 2" % xc), F.u("%s + Params.PinSq / 2" % xc), F.w("Params.PinZC - Params.PinSq / 2"), F.w("Params.PinZC + Params.PinSq / 2"), "_%d" % (k + 1))
pad(pins, sk, "Pins", "Params.PinL", reversed_=(normal_sign(sk) < 0)); finish(pins, (0.85, 0.75, 0.1))
fh = doc.addObject("PartDesign::Body", "Housing_ref")
sk = sketch(fh, "HousingOutline", "XY_Plane", "Params.FhZ_0")
rect(sk, "Params.RibXC - Params.FhW / 2", "Params.RibXC + Params.FhW / 2", "Params.FhYF", "Params.FhYR")
pad(fh, sk, "Housing", "Params.FhT")
sk = sketch(fh, "ContactProfiles", "XZ_Plane", "Params.FhYF - 1")
F = Frame(sk, (0, 2))
for k in range(4):
    xc = "Params.RibXC + (%d - 1.5) * Params.Pitch" % k
    rect(sk, F.u("%s - 0.5" % xc), F.u("%s + 0.5" % xc), F.w("Params.PinZC - 0.5"), F.w("Params.PinZC + 0.5"), "_%d" % (k + 1))
pocket(fh, sk, "Contacts", "Params.PinMate + 1.5", reversed_=(normal_sign(sk) > 0)); finish(fh, (0.2, 0.2, 0.2))
mdf = doc.addObject("PartDesign::Body", "MDF_ref")
sk = sketch(mdf, "MdfOutline", "XY_Plane", "-Params.MdfT")
rect(sk, "-375", "375", "0", "580")
pad(mdf, sk, "Mdf", "Params.MdfT"); finish(mdf, (0.55, 0.45, 0.30))
if GUI: mdf.Tip.ViewObject.Transparency = 75

PARTS = (top, mid, sleeve, tail, cs, cap)
check(PARTS)
if not globals().get("QUICK"): compare("LitterboxBrainShell", (("Top", "Top"), ("Mid", "Mid"), ("Sleeve", "Sleeve"), ("TailSleeve", "TailSleeve"), ("CapSleeve", "CapSleeve"), ("Cap", "Cap"),
                                ("ESP32_ref", "ESP32_ref"), ("LED_ref", "LED_ref"), ("USBplug_ref", "USBplug_ref"), ("TTP223_ref", "TTP223_ref"), ("Pins_ref", "Pins_ref"), ("Housing_ref", "Housing_ref")))
REFS = (esp, led, plug, padb, pins, fh, mdf)
for i, a in enumerate(PARTS if not globals().get("QUICK") else ()):
    for b in PARTS[i + 1:] + REFS:
        v = a.Shape.common(b.Shape).Volume
        if v > 1e-6: print("OVERLAP", a.Name, b.Name, round(v, 3))
if not globals().get("QUICK"): doc.saveAs(os.path.join(CAD, "brain_shell_param.FCStd"))
