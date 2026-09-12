import FreeCAD as App, FreeCADGui as Gui, Part, math
from FreeCAD import Vector as V

# HX711 shell: tray screwed to the MDF underside at the board centre, SparkFun HX711 on standoffs, feet cables enter
# under the floating wall corners. Frame: +Z toward the floor, MDF face at Z = -PLATE. Tray rebuilt from Cristian's
# Fusion STEP (HX711_Bracket.step, 2026-09-12); the cap is new.
L, W, R   = 72.0, 80.0, 15.0        # widened from 60 so the brain-ribbon exit clears the corner entries
PLATE     = 1.5
WALL      = 1.5
COMP_H    = 2.5                       # tallest thing on the HX711 board (chip, solder on the wire pads)
WALL_H    = None                      # derived below: just clears the board; set a number to override
CLR       = 0.1
CORNER_DISC_D = 15.0                  # plate kept as a quarter disc at each corner; the rest of the corner is open
SCREW     = [(-22.5,-17.5),(22.5,-17.5),(-22.5,17.5),(22.5,17.5)]
SHANK, HEAD, BOSS_D = 3.8, 7.5, 9.5
CAP_T     = 1.5
LIP_T, LIP_H = 0.5, 2.0
# SparkFun HX711 breakout 0.9" x 1.2", holes 0.7" x 1.0" apart, dia 0.13"
PCB_L, PCB_W, PCB_T = 22.86, 30.48, 0.8     # PCB_T as modelled in Fusion; SparkFun boards are usually 1.6 - measure!
PCB_HX, PCB_HY, PCB_HOLE = 8.89, 12.7, 3.3
STAND_D, STAND_H, PIN_D, PIN_H = 5.08, 1.0, 2.8, 0.8
CLIP_T, CLIP_W, CLIP_LIP, CLIP_FOOT_R = 0.8, 3.0, 0.4, 0.8   # slim catch posts: 45-deg catch, filleted root
if WALL_H is None: WALL_H = round(STAND_H + PCB_T + COMP_H + CLR, 1)
# 5th cable exit: the 5-wire ribbon to the brain (5V, 3V3, CLK, DAT, GND) leaves under the +Y end wall in a straight
# line to the brain shell's roof slot. In the assembly the tray is flipped about X, so local +Y faces the front edge
# and local X = world X; the brain's slot is centred at X = +14.2 (brain_shell: RIB_XC), so the run is straight.
RIBBON_X, RIBBON_W, RIBBON_IN = 14.2, 8.0, 7.0

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
        bite = box(min(cx, sx*L/2), max(cx, sx*L/2), min(cy, sy*W/2), max(cy, sy*W/2), -PLATE-1, 0)
        bite = bite.cut(cyl(CORNER_DISC_D/2, cx, cy, -PLATE-2, 1))
        tray = tray.cut(bite)                                              # cable entry under the wall corner
tray = tray.cut(box(RIBBON_X-RIBBON_W/2, RIBBON_X+RIBBON_W/2, W/2-WALL-RIBBON_IN, W/2+1, -PLATE-1, 0))   # brain ribbon exit through the plate; wall stays intact
for x,y in SCREW: tray = tray.cut(cyl(SHANK/2, x, y, -PLATE-1, 1))
for sx in (1,-1):
    for sy in (1,-1):
        tray = tray.fuse(cyl(STAND_D/2, sx*PCB_HX, sy*PCB_HY, -0.01, STAND_H)).fuse(cyl(PIN_D/2, sx*PCB_HX, sy*PCB_HY, STAND_H-0.01, STAND_H+PIN_H))
def prism_xz(pts, y0, y1):
    w = Part.makePolygon([V(x,y0,z) for x,z in pts] + [V(pts[0][0],y0,pts[0][1])])
    return Part.Face(w).extrude(V(0,y1-y0,0))
def catch_post(x_face, inward, y0, y1):
    """post rising from the plate beside the PCB edge, 45-deg catch over it (no flat overhang), concave root fillet"""
    xo = x_face - inward*CLIP_T
    z0 = STAND_H + PCB_T + CLR                                           # catch starts CLR above the PCB top
    p = box(min(x_face,xo), max(x_face,xo), y0, y1, -0.01, z0+1.0)
    p = p.fuse(prism_xz([(x_face, z0), (x_face+inward*CLIP_LIP, z0+CLIP_LIP), (x_face, z0+1.0)], y0, y1))
    foot = box(min(xo, xo-inward*CLIP_FOOT_R), max(xo, xo-inward*CLIP_FOOT_R), y0, y1, -0.01, CLIP_FOOT_R)
    foot = foot.cut(Part.makeCylinder(CLIP_FOOT_R, y1-y0+2, V(xo-inward*CLIP_FOOT_R, y0-1, CLIP_FOOT_R), V(0,1,0)))
    return p.fuse(foot)
for sx in (1,-1):                                                          # catch posts on the PCB's long edges
    tray = tray.fuse(catch_post(sx*(PCB_L/2+CLR), -sx, -CLIP_W/2, CLIP_W/2))
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
# four 3-way Dupont housings (7.62 x 2.54 x 14) lying flat at the +-Y ends between the bosses, one per foot cable,
# each a few mm from its corner cable entry
DUP_XY = [(sx*9.0, sy*19.8) for sx in (1,-1) for sy in (1,-1)]
dup = None
for x,y in DUP_XY:
    b = box(x-7, x+7, y-3.81, y+3.81, CLR, CLR+2.54)
    dup = b if dup is None else dup.fuse(b)

def add(name, shape, color, transp=0):
    o = doc.addObject("Part::Feature", name); o.Shape = shape
    o.ViewObject.ShapeColor = color; o.ViewObject.Transparency = transp; return o
add("Tray", tray, (0.93,0.92,0.88)); add("Cap", cap, (0.93,0.92,0.88))
add("HX711_ref", pcb, (0.8,0.1,0.1)); add("Dupont_ref", dup, (0.85,0.75,0.1))
doc.recompute()
PARTS = ("Tray","Cap")
for nm in PARTS:
    s = doc.getObject(nm).Shape; bb = s.BoundBox
    print(nm, "valid:", s.isValid(), "solids:", len(s.Solids), "vol:", round(s.Volume,1), "z:", round(bb.ZMin,2), "..", round(bb.ZMax,2))
for a,b in (("Tray","Cap"),("Tray","HX711_ref"),("Cap","HX711_ref"),("Tray","Dupont_ref"),("Cap","Dupont_ref")):
    v = doc.getObject(a).Shape.common(doc.getObject(b).Shape).Volume
    if v>1e-6: print("OVERLAP", a, b, round(v,3))
def dist(a,b): return round(doc.getObject(a).Shape.distToShape(doc.getObject(b).Shape)[0],3)
print("gaps: tray-cap", dist("Tray","Cap"), " cap-pcb", dist("Cap","HX711_ref"), " tray-dupont", dist("Tray","Dupont_ref"), " cap-dupont", dist("Cap","Dupont_ref"))
print("ribbon exit X", RIBBON_X-RIBBON_W/2, "..", RIBBON_X+RIBBON_W/2, " corner entry starts at X", (L/2-R), " gap", round((L/2-R)-(RIBBON_X+RIBBON_W/2),2), " opening height", PLATE)
print("wall height", WALL_H, " cap underside over dupont", round(WALL_H-(CLR+2.54),2), " over PCB top", round(WALL_H-(STAND_H+PCB_T),2))
print("shell height:", round(doc.getObject("Cap").Shape.BoundBox.ZMax + PLATE, 2), " screw: plastic under head", round(1.3+CLR+PLATE,2), "-> 4x16 bites", round(16-(1.3+CLR+PLATE),1), "mm  cable gap under wall corners", PLATE)
Gui.SendMsgToActiveView("ViewFit")

# ---- outputs next to this script: <part>.stl (print) + .step, and the FreeCAD document
import os as _os
_CAD = _os.path.dirname(_os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'
for _nm in PARTS:
    export_stl(doc.getObject(_nm).Shape, _os.path.join(_CAD, 'hx711_%s.stl' % _nm.lower()))
    doc.getObject(_nm).Shape.exportStep(_os.path.join(_CAD, 'hx711_%s.step' % _nm.lower()))
doc.saveAs(_os.path.join(_CAD, 'hx711.FCStd'))
