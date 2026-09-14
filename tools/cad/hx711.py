import FreeCAD as App, FreeCADGui as Gui, Part, math
from FreeCAD import Vector as V

# HX711 shell: tray screwed to the MDF underside at the board centre, SparkFun HX711 on standoffs, feet cables enter
# under the floating wall corners. Frame: +Z toward the floor, MDF face at Z = -PLATE. Tray rebuilt from Cristian's
# Fusion STEP (HX711_Bracket.step, 2026-09-12); the cap is new.
L, W, R   = 76.0, 80.0, 15.0        # widened from 60 so the brain-ribbon exit clears the corner entries
PLATE     = 1.5
WALL      = 1.5
COMP_H    = 2.5                       # tallest thing on the HX711 board (chip, solder on the wire pads)
WALL_H    = None                      # derived below: just clears the board; set a number to override
CLR       = 0.1
CORNER_DISC_D = 15.0                  # plate kept as a quarter disc at each corner; the rest of the corner is open
SCREW     = [(22.5,-17.5),(-22.5,17.5)]   # two, on the diagonal away from the ribbon exit (+X, +Y end); the cap's rim in the rebate does the rest
SHANK, HEAD, BOSS_D = 3.8, 7.5, 9.5
CAP_T     = 1.5
LIP_T, LIP_H = 0.5, 2.0
# SparkFun HX711 breakout 0.9" x 1.2", holes 0.7" x 1.0" apart, dia 0.13"
PCB_L, PCB_W, PCB_T = 22.86, 30.48, 0.8     # PCB_T as modelled in Fusion; SparkFun boards are usually 1.6 - measure!
PCB_HX, PCB_HY, PCB_HOLE = 8.89, 12.7, 3.3
STAND_D, STAND_H, PIN_D, PIN_H = 5.08, 1.0, 2.8, 0.8
RING_W, RING_H = 0.6, 0.4             # embossed ring on the plate just outside each cap boss's footprint: keep leads out of it
# cable clips on the plate: a pair of posts whose tips lean toward each other, a lead bundle pushes in past the tips and
# stays. Three per side along the +-X walls (leads running along Y) and two on each +-Y wall (leads along X); on +Y the
# ribbon exit takes the +X half, so that pair sits at X -12 and 0. Printed plate-down the tips are CLIP_TIP overhangs
# over CLIP_TIP_H of height.
CLIP_XY = [(sx*31.0, y, 'y') for sx in (1,-1) for y in (-20.0, 0.0, 20.0)] + [(x, -33.0, 'x') for x in (-12.0, 12.0)] + [(x, 33.0, 'x') for x in (-12.0, 0.0)]
POST_W, POST_L, POST_H = 1.0, 2.0, 3.0     # post: across the lead run x along it x tall (cap underside is at WALL_H)
CLIP_GAP, CLIP_TIP, CLIP_TIP_H = 2.2, 0.85, 0.85 # gap at the plate; each tip leans in CLIP_TIP over the top CLIP_TIP_H (45 deg) -> 0.5 at the tips
POST_FOOT_R = 0.8                          # root fillet on a post's three outer faces (not the gap side)
# PCB catch on each long edge: a gate — two stout posts bridged at the top by a thin bar carrying the lip. Pressing the
# board in bows the bar outward by LIP (about 1.5 % strain over GATE_L) instead of bending a 2 mm post, which PLA can't do.
# The lip has a flat underside (holds) and a 45-deg top (lets the board in). Printed plate-down the bar is a bridge and
# the lip's underside an overhang: Cristian prints the tray with supports.
GATE_L, GATE_POST, GATE_T, GATE_FOOT_R = 14.0, 3.0, 2.0, 1.5   # bar span between the posts, post length along the edge, post thickness, root fillet
BAR_T, BAR_H, LIP, LIP_L = 1.0, 2.0, 0.5, 6.0                  # bar thickness (flexes), height, lip reach over the board, lip length
NOTCH_H, NOTCH_H_CELL = 2.9, 2.1      # channels.py: the RIBBON bar through the ribbon exit, the CELL bars under the wall corners
# 5th cable exit: the 5-wire ribbon to the brain (5V, 3V3, CLK, DAT, GND) leaves under the +Y end wall toward the
# brain shell's roof slot. In the assembly the tray is flipped about X, so local +Y faces the front edge and local
# X = world X; the brain's slot is centred at X = +13.6 (brain_shell: RIB_XC), so the run is straight. The opening is
# the RIBBON bar's notch through the plate and the wall's foot; the bar ends inside on the plate step (channels.py).
RIBBON_X, RIBBON_W, RIBBON_IN = 13.6, 16.5, 7.0
if WALL_H is None: WALL_H = round(STAND_H + PCB_T + COMP_H + CLR, 1)

for d in list(App.listDocuments()):
    if d == "HX711Shell": App.closeDocument(d)
doc = App.newDocument("HX711Shell")

def export_stl(shape, path):
    import MeshPart
    MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.05, AngularDeflection=0.35, Relative=False).write(path)
def box(x0,x1,y0,y1,z0,z1): return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))
def cyl(r,x,y,z0,z1): return Part.makeCylinder(r, z1-z0, V(x,y,z0))
def rbox(x0,x1,y0,y1,z0,z1,r):
    b = box(x0,x1,y0,y1,z0,z1)
    es=[e for e in b.Edges if abs(e.tangentAt(e.FirstParameter).z)>0.999]
    return b.makeFillet(r, es) if r>0 else b
def fillet_top(shape, z, r):
    es=[e for e in shape.Edges if abs(e.BoundBox.ZMin-z)<1e-6 and abs(e.BoundBox.ZMax-z)<1e-6]
    try: return shape.makeFillet(r, es)
    except Exception as ex: print("fillet skipped:", ex); return shape
def ring(t_out, t_in, z0, z1):
    return rbox(-L/2+t_out, L/2-t_out, -W/2+t_out, W/2-t_out, z0, z1, R-t_out).cut(
           rbox(-L/2+t_in,  L/2-t_in,  -W/2+t_in,  W/2-t_in,  z0-1, z1+1, R-t_in))

# ---------------- TRAY ----------------
tray = rbox(-L/2, L/2, -W/2, W/2, -PLATE, WALL_H, R)
tray = tray.cut(rbox(-L/2+WALL, L/2-WALL, -W/2+WALL, W/2-WALL, 0, WALL_H+1, R-WALL))
for sx in (1,-1):
    for sy in (1,-1):
        cx, cy = sx*(L/2-R), sy*(W/2-R)                                   # corner centre
        bite = box(min(cx, sx*L/2), max(cx, sx*L/2), min(cy, sy*W/2), max(cy, sy*W/2), -PLATE-1, NOTCH_H_CELL-PLATE)
        bite = bite.cut(cyl(CORNER_DISC_D/2, cx, cy, -PLATE-2, 1))
        tray = tray.cut(bite)                                              # cable entry under the wall corner
tray = tray.cut(box(RIBBON_X-RIBBON_W/2, RIBBON_X+RIBBON_W/2, W/2-WALL-RIBBON_IN, W/2+1, -PLATE-1, NOTCH_H-PLATE))   # brain ribbon exit: plate and the wall's foot
for x,y in SCREW: tray = tray.cut(cyl(SHANK/2, x, y, -PLATE-1, 1))
for sx in (1,-1):
    for sy in (1,-1):
        tray = tray.fuse(cyl(STAND_D/2, sx*PCB_HX, sy*PCB_HY, -0.01, STAND_H)).fuse(cyl(PIN_D/2, sx*PCB_HX, sy*PCB_HY, STAND_H-0.01, STAND_H+PIN_H))
def prism_xz(pts, y0, y1):
    w = Part.makePolygon([V(x,y0,z) for x,z in pts] + [V(pts[0][0],y0,pts[0][1])])
    return Part.Face(w).extrude(V(0,y1-y0,0))
def catch_gate(x_face, inward):
    """two posts beside the PCB edge, a bar bridging their tops from z0 (CLR above the board) up BAR_H, the lip on the
    bar's middle: flat underside at z0 holds the board down, 45-deg top face pushes the bar out on the way in."""
    z0 = STAND_H + PCB_T + CLR
    xo = x_face - inward*GATE_T
    g = None
    for sy in (1,-1):
        y0, y1 = min(sy*GATE_L/2, sy*(GATE_L/2+GATE_POST)), max(sy*GATE_L/2, sy*(GATE_L/2+GATE_POST))
        p = box(min(x_face,xo), max(x_face,xo), y0, y1, -0.01, z0+BAR_H)
        foot = box(min(xo, xo-inward*GATE_FOOT_R), max(xo, xo-inward*GATE_FOOT_R), y0, y1, -0.01, GATE_FOOT_R)
        foot = foot.cut(Part.makeCylinder(GATE_FOOT_R, y1-y0+2, V(xo-inward*GATE_FOOT_R, y0-1, GATE_FOOT_R), V(0,1,0)))
        p = p.fuse(foot); g = p if g is None else g.fuse(p)
    xb = x_face - inward*BAR_T
    g = g.fuse(box(min(x_face,xb), max(x_face,xb), -GATE_L/2-0.01, GATE_L/2+0.01, z0, z0+BAR_H))
    g = g.fuse(prism_xz([(x_face, z0), (x_face+inward*LIP, z0), (x_face, z0+LIP)], -LIP_L/2, LIP_L/2))
    return g
for sx in (1,-1):                                                          # gates on the PCB's long edges
    tray = tray.fuse(catch_gate(sx*(PCB_L/2+CLR), -sx))
def root_fillet(x0, x1, y0, y1, out, r):
    """concave fillet of radius r along the bottom of a vertical face of a body standing on the plate: the face is the
    segment x0..x1 at y0 (== y1) or y0..y1 at x0 (== x1); 'out' = (dx, dy) is the unit normal away from the body"""
    dx, dy = out
    if dx:
        b = box(min(x0, x0+dx*r), max(x0, x0+dx*r), y0, y1, -0.01, r)
        return b.cut(Part.makeCylinder(r, y1-y0+2, V(x0+dx*r, y0-1, r), V(0,1,0)))
    b = box(x0, x1, min(y0, y0+dy*r), max(y0, y0+dy*r), -0.01, r)
    return b.cut(Part.makeCylinder(r, x1-x0+2, V(x0-1, y0+dy*r, r), V(1,0,0)))
def clip(x, y, run):                                                       # leads run along 'run' between the two posts
    s = None
    for sx in (1,-1):
        xi = sx*CLIP_GAP/2; xo = xi + sx*POST_W                                # built with the leads along Y, about the origin
        p = box(min(xi,xo), max(xi,xo), -POST_L/2, POST_L/2, -0.01, POST_H)
        p = p.fuse(prism_xz([(xi, POST_H-CLIP_TIP_H), (xi-sx*CLIP_TIP, POST_H), (xi, POST_H)], -POST_L/2, POST_L/2))
        p = p.fuse(root_fillet(xo, xo, -POST_L/2, POST_L/2, (sx, 0), POST_FOOT_R))                 # outer face
        for sy in (1,-1):                                                                          # end faces
            p = p.fuse(root_fillet(min(xi,xo), max(xi,xo), sy*POST_L/2, sy*POST_L/2, (0, sy), POST_FOOT_R))
        s = p if s is None else s.fuse(p)
    if run == 'x': s.rotate(V(0,0,0), V(0,0,1), 90)
    s.translate(V(x, y, 0)); return s
for x,y,run in CLIP_XY: tray = tray.fuse(clip(x, y, run))
for x,y in SCREW: tray = tray.fuse(cyl(BOSS_D/2+0.3+RING_W, x, y, -0.01, RING_H).cut(cyl(BOSS_D/2+0.3, x, y, -1, 1)))   # boss footprint rings
tray = tray.cut(ring(WALL-LIP_T-CLR, WALL+0.2, WALL_H-LIP_H, WALL_H+1))     # rebate in the wall top for the cap rim
tray = tray.removeSplitter()

# ---------------- CAP ----------------
zc0 = WALL_H
cap = fillet_top(rbox(-L/2, L/2, -W/2, W/2, zc0, zc0+CAP_T, R), zc0+CAP_T, 1.0)
cap = cap.fuse(ring(WALL-LIP_T, WALL, zc0-LIP_H+CLR, zc0+0.01))            # rim into the rebate
for x,y in SCREW:
    cap = cap.fuse(cyl(BOSS_D/2, x, y, CLR, zc0+0.01))                     # boss down to CLR above the plate
for x,y in SCREW:
    cap = cap.cut(cyl(SHANK/2, x, y, -1, zc0+CAP_T+1)).cut(cyl(HEAD/2, x, y, CLR+1.3, zc0+CAP_T+1))
cap = cap.removeSplitter()
mouth = [e for e in cap.Edges if isinstance(e.Curve, Part.Circle) and abs(e.Curve.Radius-HEAD/2)<0.01 and abs(e.BoundBox.ZMin-(zc0+CAP_T))<1e-6]
try: cap = cap.makeFillet(1.0, mouth)
except Exception as ex: print("mouth fillet skipped:", ex)

# ---------------- references ----------------
pcb = box(-PCB_L/2, PCB_L/2, -PCB_W/2, PCB_W/2, STAND_H, STAND_H+PCB_T)
for sx in (1,-1):
    for sy in (1,-1): pcb = pcb.cut(cyl(PCB_HOLE/2, sx*PCB_HX, sy*PCB_HY, 0, 5))

def add(name, shape, color, transp=0):
    o = doc.addObject("Part::Feature", name); o.Shape = shape
    if App.GuiUp: o.ViewObject.ShapeColor = color; o.ViewObject.Transparency = transp
    return o
add("Tray", tray, (0.93,0.92,0.88)); add("Cap", cap, (0.93,0.92,0.88))
add("HX711_ref", pcb, (0.8,0.1,0.1))
doc.recompute()
PARTS = ("Tray","Cap")
for nm in PARTS:
    s = doc.getObject(nm).Shape; bb = s.BoundBox
    print(nm, "valid:", s.isValid(), "solids:", len(s.Solids), "vol:", round(s.Volume,1), "z:", round(bb.ZMin,2), "..", round(bb.ZMax,2))
for a,b in (("Tray","Cap"),("Tray","HX711_ref"),("Cap","HX711_ref")):
    v = doc.getObject(a).Shape.common(doc.getObject(b).Shape).Volume
    if v>1e-6: print("OVERLAP", a, b, round(v,3))
def dist(a,b): return round(doc.getObject(a).Shape.distToShape(doc.getObject(b).Shape)[0],3)
print("gaps: tray-cap", dist("Tray","Cap"), " cap-pcb", dist("Cap","HX711_ref"), " clip tips under the cap", round(WALL_H-POST_H,2), " ring to boss", 0.3)
print("ribbon exit X", RIBBON_X-RIBBON_W/2, "..", RIBBON_X+RIBBON_W/2, " corner entry starts at X", (L/2-R), " gap", round((L/2-R)-(RIBBON_X+RIBBON_W/2),2),
      " opening", RIBBON_W, "x", NOTCH_H, "reaching", RIBBON_IN, "inside the wall")
print("wall height", WALL_H, " over PCB top", round(WALL_H-(STAND_H+PCB_T),2), " clip gap", CLIP_GAP, "at the plate,", round(CLIP_GAP-2*CLIP_TIP,2), "at the tips")
print("shell height:", round(doc.getObject("Cap").Shape.BoundBox.ZMax + PLATE, 2), " screw: plastic under head", round(1.3+CLR+PLATE,2), "-> 4x16 bites", round(16-(1.3+CLR+PLATE),1), "mm  notch under wall corners", NOTCH_H_CELL)
if App.GuiUp: Gui.SendMsgToActiveView("ViewFit")

# ---- outputs next to this script: <part>.stl (print) + .step, and the FreeCAD document (skipped when the caller
# seeds the namespace with EXPORT = False, e.g. assembly.py previewing)
import os as _os
if globals().get('EXPORT', True):
    _CAD = _os.path.dirname(_os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor-enclosure/tools/cad'
    for _nm in PARTS:
        export_stl(doc.getObject(_nm).Shape, _os.path.join(_CAD, 'hx711_%s.stl' % _nm.lower()))
        doc.getObject(_nm).Shape.exportStep(_os.path.join(_CAD, 'hx711_%s.step' % _nm.lower()))
    doc.saveAs(_os.path.join(_CAD, 'hx711.FCStd'))
