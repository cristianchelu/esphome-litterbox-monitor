import os, sys, math, importlib
import FreeCAD as App, Part, Sketcher
from FreeCAD import Vector as V

# Cable channels taped to the MDF underside, as a PartDesign document: arched profile (short straight walls +
# semicircular crown) with two tape flanges, built along +X with the tape face at Z = 0 and the body hanging to -Z.
# Runs are split into sections <= MaxLen for the A1 mini; every section but the last of a run carries a 6 mm spigot
# (the arch continued as a thin inward skin) that slides into the plain -X end of the next. The run lengths are sheet
# formulas from the layout (feet, HX711 tray, brain shell), so the sections follow the assembly. One Body per section.

CAD = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'
if CAD not in sys.path: sys.path.insert(0, CAD)
import pdlib; importlib.reload(pdlib)
from pdlib import *

PARAMS = [
 ("Profile", None, None),
 ("InnerW",    8.0, "bore width: a flat 5-wire ribbon"),
 ("Wall",      1.2, "channel wall"),
 ("WallH",     1.0, "straight wall under the tape face before the crown (room for the ribbon's edges)"),
 ("Flange",    4.0, "tape flange each side"),
 ("FlangeT",   1.2, "flange thickness"),
 ("Clr",       0.1, "spigot skin sits this far inside the next section's bore"),
 ("SpigotL",   6.0, "spigot length past the section end"),
 ("SpigotT",   0.6, "spigot skin thickness"),
 ("SpigotRoot",1.0, "spigot root grown into this section's wall"),
 ("MaxLen",  170.0, "longest printable section (A1 mini bed)"),
 ("Gap",       2.0, "run stops this short of each end fitting"),
 ("Layout (copied from the assembly)", None, None),
 ("MdfW",    750.0, "KOMPLEMENT underside, X (front edge)"),
 ("MdfD",    580.0, "Y (into the board)"),
 ("FootInX",  60.0, "foot centre in from the short edges"),
 ("FootInY",  40.0, "foot centre in from the long edges"),
 ("FootL",    55.0, "foot base length; the wire leaves the +X end, which points at the board centre"),
 ("TrayL",    72.0, "HX711 tray at the board centre"),
 ("TrayW",    80.0, ""),
 ("TrayR",    15.0, "tray corner radius: the cable ducks under the wall on the corner arc"),
 ("RibbonX",  14.2, "HX711 ribbon exit X = brain roof slot X: the brain run is straight along Y"),
 ("BrainT",   15.9, "brain shell tail depth from the front edge (brain_shell: T)"),
 ("Run lengths (derived)", None, None),
 ("Dx",       "=MdfW / 2 - FootInX", "foot 1 to board centre, X"),
 ("Dy",       "=MdfD / 2 - FootInY", "Y"),
 ("FootDist",       "=hypot(Dx; Dy)", "foot centre to board centre"),
 ("Cx",       "=TrayL / 2 - TrayR", "tray corner arc centre from the board centre"),
 ("Cy",       "=TrayW / 2 - TrayR", ""),
 ("CornerDist",       "=hypot(Dx - Cx; Dy - Cy)", "tray corner arc centre to foot centre"),
 ("Ex",       "=Dx * (1 - FootL / (2 * FootDist)) - Cx - TrayR * (Dx - Cx) / CornerDist", "foot wire exit to tray corner entry, X"),
 ("Ey",       "=Dy * (1 - FootL / (2 * FootDist)) - Cy - TrayR * (Dy - Cy) / CornerDist", "Y"),
 ("FootRun",  "=hypot(Ex; Ey) - 2 * Gap", "foot -> HX711 run (all four feet alike)"),
 ("FootN",    "=ceil(FootRun / MaxLen)", "sections"),
 ("FootSec",  "=FootRun / FootN", "section length"),
 ("BrainRun", "=MdfD / 2 - TrayW / 2 - BrainT - 2 * Gap", "HX711 -> brain run"),
 ("BrainN",   "=ceil(BrainRun / MaxLen)", "sections"),
 ("BrainSec", "=BrainRun / BrainN", "section length"),
]
doc, ss = init("CableChannelParam", PARAMS)
vals = pdlib.vals

def u_profile(sk, F, r_out, r_in, flange=None, flange_t=None, tag=""):
    """closed U (open at the top, on the sketch's x axis): straight walls WallH down, semicircular crown, wall between
    r_in and r_out; optional flanges along the top edge. Right side dimensioned, left side symmetric about the axis."""
    ro, ri, hw = ev(r_out), ev(r_in), vals["WallH"]
    fl, ft = (ev(flange), ev(flange_t)) if flange else (0.0, 0.0)
    P = F.P
    L = lambda a, b: sk.addGeometry(Part.LineSegment(P(*a), P(*b)), False)
    pp = 1 if F.reflected else 2                  # which arc end lands on the +Y side; the other is 3 - pp
    def arc(r):
        a0, a1 = (math.pi, 2 * math.pi) if F.s[1] > 0 else (0, math.pi)
        return sk.addGeometry(Part.ArcOfCircle(Part.Circle(P(0, -hw), V(0, 0, 1), r), a0, a1), False)
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    # right side down: A(ro+fl,0) B(ro+fl,-ft) C(ro,-ft) D(ro,-hw); crown D'..D; left side up; top A'..G'; inner G'H' H'..H HG GA
    if flange:
        ab = L((ro + fl, 0), (ro + fl, -ft)); bc = L((ro + fl, -ft), (ro, -ft)); cd = L((ro, -ft), (ro, -hw))
        dc_ = L((-ro, -hw), (-ro, -ft)); cb_ = L((-ro, -ft), (-ro - fl, -ft)); ba_ = L((-ro - fl, -ft), (-ro - fl, 0))
        right, left = [ab, bc, cd], [dc_, cb_, ba_]
        C("Vertical", ab); C("Horizontal", bc); C("Vertical", cd)
    else:
        ad = L((ro, 0), (ro, -hw)); da_ = L((-ro, -hw), (-ro, 0))
        right, left = [ad], [da_]
        C("Vertical", ad)
    outer = arc(ro)
    ag_ = L((-ro - fl, 0), (-ri, 0)); gh_ = L((-ri, 0), (-ri, -hw)); inner = arc(ri); hg = L((ri, -hw), (ri, 0)); ga = L((ri, 0), (ro + fl, 0))
    for a, b in zip(right, right[1:]): C("Coincident", a, 2, b, 1)
    for a, b in zip(left, left[1:]): C("Coincident", a, 2, b, 1)
    C("Coincident", right[-1], 2, outer, pp); C("Coincident", outer, 3 - pp, left[0], 1)       # D, D'
    C("Coincident", left[-1], 2, ag_, 1); C("Coincident", ag_, 2, gh_, 1)                       # A', G'
    C("Coincident", gh_, 2, inner, 3 - pp); C("Coincident", inner, pp, hg, 1)                   # H', H
    C("Coincident", hg, 2, ga, 1); C("Coincident", ga, 2, right[0], 1)                          # G, A
    C("Vertical", gh_); C("Vertical", hg); C("Horizontal", ag_); C("Horizontal", ga)
    C("PointOnObject", ga, 1, -1)                                             # the open top lies on the tape face
    C("Horizontal", outer, 3, outer, pp); C("PointOnObject", outer, 3, -2)    # crown centred on the axis, level with the wall foot
    C("Horizontal", inner, 3, inner, pp); C("PointOnObject", inner, 3, -2)
    C("Horizontal", right[-1], 2, hg, 1)                 # inner crown level with the outer one
    C("Horizontal", outer, 3, outer, 3 - pp)             # the arcs' far ends are their own free parameter (the angle):
    C("Horizontal", inner, 3, inner, 3 - pp)             # level with the centre makes them true semicircles
    C("Symmetric", ga, 2, ag_, 1, -2)                    # A / A'
    if flange: C("Symmetric", bc, 1, cb_, 2, -2); C("Symmetric", bc, 2, cb_, 1, -2)     # B / B', C / C'
    dist_constraint(sk, "DistanceX", -1, 1, right[-1], 2, F.u(r_out), "r_out" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, right[-1], 2, F.w("-Params.WallH"), "wall_h" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, ga, 1, F.u(r_in), "r_in" + tag)
    if flange:
        dist_constraint(sk, "DistanceX", bc, 2, bc, 1, F.u(flange), "flange" + tag)
        dist_constraint(sk, "DistanceY", -1, 1, bc, 1, F.w("-(%s)" % flange_t), "flange_t" + tag)

def section(name, length, spigot):
    body = doc.addObject("PartDesign::Body", name)
    sk = sketch(body, name + "_Profile", "YZ_Plane", "0")
    F = Frame(sk, (1, 2))
    u_profile(sk, F, "Params.InnerW / 2 + Params.Wall", "Params.InnerW / 2", "Params.Flange", "Params.FlangeT")
    pad(body, sk, name + "_Arch", length, reversed_=(F.normal_sign < 0))
    if spigot:
        sk = sketch(body, name + "_SpigotRootProfile", "YZ_Plane", "%s(%s - Params.SpigotRoot)" % ("" if F.normal_sign > 0 else "-", length))
        u_profile(sk, Frame(sk, (1, 2)), "Params.InnerW / 2 + 0.05", "Params.InnerW / 2 - Params.Clr - Params.SpigotT")
        pad(body, sk, name + "_SpigotRoot", "Params.SpigotRoot", reversed_=(F.normal_sign < 0))
        sk = sketch(body, name + "_SpigotProfile", "YZ_Plane", "%s(%s)" % ("" if F.normal_sign > 0 else "-", length))
        u_profile(sk, Frame(sk, (1, 2)), "Params.InnerW / 2 - Params.Clr", "Params.InnerW / 2 - Params.Clr - Params.SpigotT")
        pad(body, sk, name + "_Spigot", "Params.SpigotL", reversed_=(F.normal_sign < 0))
    finish(body, (0.55, 0.6, 0.7))
    return body

bodies = []
for run, n, sec in (("FootRun", int(vals["FootN"]), "Params.FootSec"), ("BrainRun", int(vals["BrainN"]), "Params.BrainSec")):
    for j in range(n):
        bodies.append(section("%s_%dof%d" % (run, j + 1, n), sec, spigot=(j < n - 1)))
        if GUI: bodies[-1].Placement = App.Placement(V(0, 0, -30 * (len(bodies) - 1)), App.Rotation())   # spread out for viewing only
print("foot run %.1f mm -> %d x %.2f | brain run %.1f mm -> %d x %.2f" % (vals["FootRun"], vals["FootN"], vals["FootSec"], vals["BrainRun"], vals["BrainN"], vals["BrainSec"]))
check(bodies)
doc.saveAs(os.path.join(CAD, "channel_param.FCStd"))
