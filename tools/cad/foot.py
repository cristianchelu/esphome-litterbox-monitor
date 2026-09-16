import FreeCAD as App, FreeCADGui as Gui, Part, math
from FreeCAD import Vector as V

# Load-cell foot: base screwed to the MDF underside, 26x26 cantilever cell clamped by the cap, plastic foot to the floor.
# Frame: origin at the foot centre, +Z toward the floor, MDF face at Z = -PLATE (below the base plate). Rebuilt from
# the Fusion STEP (tools/cad reference) 2026-09-12.
L, W, R    = 55.0, 50.0, 15.0        # base/cap outline, corner radius
PLATE      = 1.5                     # base plate
WALL       = 1.5                     # outer wall and ribs
WALL_H     = 3.6                     # wall/rib top above the plate top (Z=0)
CLR        = 0.1                     # print-to-print
CLR_METAL  = 0.2                     # around the aluminium body
SCREW      = [(-17.5,-15.0),(17.5,-15.0),(-17.5,15.0),(17.5,15.0)]
SHANK, HEAD = 3.8, 7.5
BOSS_D     = 9.5
CAP_T      = 1.5
# cell: 26x26x1.6 R6.5 aluminium, 19x21 R4 window offset 1.5 in X, wires leave under the body toward +X
CELL_S, CELL_T, CELL_R = 26.0, 1.6, 6.5
CELL_X0 = -14.5; CELL_X1 = CELL_X0+CELL_S
WIN_X0, WIN_X1, WIN_HY, WIN_R = -12.5, 6.5, 10.5, 4.0
PLAT_H     = 2.0                     # platform the cell sits on, above the plate top
BITE_D, BITE_X = 8.0, 14.2           # wire drop at the platform's +X edge
RIB_Y      = (6.0, 7.5)              # rib pair each side of the channel notch
RIB_X      = ((-8.0,-6.5),(3.5,5.0)) # rib pair top/bottom
EXIT_X0, EXIT_HY, EXIT_H = 20.5, 5.25, 2.1  # notch under the +X wall: 10.5 x 2.1, the CELL channel bar (channels.py) ends inside on the plate step
HOUSE_H  = 4.5                       # housing height above the cap plate
HOUSE_IX = 12.6                      # half-size of the housing at the S-curve inflection (mid height)
HOUSE_IR = 7.6                       # corner radius there (centres at +-5, same as the cavity)
HOUSE_FR = 3.0                       # convex top round-over and concave base fillet, tangent S (no straight wall)
RAMP_X1, RAMP_HY, RAMP_Z = 15.5, 4.0, 1.93   # wire wedge under the cap: cavity wall -> RAMP_X1, rises RAMP_Z at the wall
CAV_S, CAV_R = 22.0, 6.0             # cavity over the strain section / foot block
BUTTON_D, BUTTON_H = 10.5, 6.5       # plastic foot
FOOT_BLK = (11.0, 19.5, 3.0)
HOLE_D   = BUTTON_D + 1.0
SHIMS    = (1.0,)                    # one optional levelling shim kept; add thicknesses here if needed

for d in list(App.listDocuments()):
    if d == "LoadCellFoot": App.closeDocument(d)
doc = App.newDocument("LoadCellFoot")

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

# ---------------- BASE ----------------
base = rbox(-L/2, L/2, -W/2, W/2, -PLATE, WALL_H, R)
base = base.cut(rbox(-L/2+WALL, L/2-WALL, -W/2+WALL, W/2-WALL, 0, WALL_H+1, R-WALL))
platform = rbox(CELL_X0-CLR_METAL, CELL_X1+CLR_METAL, -CELL_S/2-CLR_METAL, CELL_S/2+CLR_METAL, 0, PLAT_H, CELL_R+CLR_METAL)
platform = platform.cut(rbox(WIN_X0, WIN_X1, -WIN_HY, WIN_HY, -1, PLAT_H+1, WIN_R))
platform = platform.cut(cyl(BITE_D/2, BITE_X, 0, -1, PLAT_H+1))
base = base.fuse(platform)
for y0,y1 in (RIB_Y, (-RIB_Y[1],-RIB_Y[0])):
    base = base.fuse(box(-L/2+WALL-0.01, CELL_X0-CLR_METAL, y0, y1, 0, WALL_H))
    base = base.fuse(box(CELL_X1+CLR_METAL, L/2-WALL+0.01, y0, y1, 0, WALL_H))
for x0,x1 in RIB_X:
    base = base.fuse(box(x0, x1, -W/2+WALL-0.01, -CELL_S/2-CLR_METAL, 0, WALL_H))
    base = base.fuse(box(x0, x1, CELL_S/2+CLR_METAL, W/2-WALL+0.01, 0, WALL_H))
base = base.cut(box(EXIT_X0, L/2+1, -EXIT_HY, EXIT_HY, -PLATE-1, EXIT_H-PLATE))   # channel notch under the +X wall, into the wall's foot
for x,y in SCREW: base = base.cut(cyl(SHANK/2, x, y, -PLATE-1, 1))
base = base.removeSplitter()

# ---------------- CAP ----------------
zc0 = WALL_H                                   # cap plate underside sits on the wall tops
cap = rbox(-L/2, L/2, -W/2, W/2, zc0, zc0+CAP_T, R)
cap = fillet_top(cap, zc0+CAP_T, 1.0)
def housing(z_base, z_top):
    """S-profile (convex R top, concave R base) swept around the rounded square at the inflection height."""
    h, r, R = HOUSE_IX, HOUSE_IR, HOUSE_FR
    zi = (z_base + z_top)/2                                    # inflection height
    k = h - r; q = r/math.sqrt(2)
    def arc(p1, pm, p2): return Part.Arc(V(*p1), V(*pm), V(*p2)).toShape()
    def line(p1, p2): return Part.LineSegment(V(*p1), V(*p2)).toShape()
    path = Part.Wire([line((0,-h,zi),(k,-h,zi)), arc((k,-h,zi),(k+q,-k-q,zi),(h,-k,zi)), line((h,-k,zi),(h,k,zi)),
                      arc((h,k,zi),(k+q,k+q,zi),(k,h,zi)), line((k,h,zi),(-k,h,zi)), arc((-k,h,zi),(-k-q,k+q,zi),(-h,k,zi)),
                      line((-h,k,zi),(-h,-k,zi)), arc((-h,-k,zi),(-k-q,-k-q,zi),(-k,-h,zi)), line((-k,-h,zi),(0,-h,zi))])
    # profile in the plane X=0 at the path start (0,-h,zi); outward is -Y
    dz = (z_top - z_base)/2                                    # half height; centres sit dz apart in Z
    dy = math.sqrt(R**2 - (dz-R)**2)                            # centres 2R apart, inflection at their midpoint
    yt = -h + dy                                               # top-flat end (top arc centre Y)
    yb = -h - dy                                               # base tangent point (base arc centre Y)
    c1 = (yt, z_top - R); c2 = (yb, z_base + R)
    def onarc(c, ang): return (0, c[0] + R*math.cos(math.radians(ang)), c[1] + R*math.sin(math.radians(ang)))
    a_i1 = math.degrees(math.atan2(zi - c1[1], -h - c1[0]))    # inflection seen from c1
    a_i2 = math.degrees(math.atan2(zi - c2[1], -h - c2[0]))
    prof = Part.Wire([arc((0,yt,z_top), onarc(c1,(90+a_i1)/2), (0,-h,zi)),
                      arc((0,-h,zi), onarc(c2,(a_i2-90)/2), (0,yb,z_base)),
                      line((0,yb,z_base),(0,yb,z_base-0.1)), line((0,yb,z_base-0.1),(0,-6.0,z_base-0.1)),
                      line((0,-6.0,z_base-0.1),(0,-6.0,z_top)), line((0,-6.0,z_top),(0,yt,z_top))])
    ring = path.makePipeShell([prof], True, False)
    core = box(-6.5,6.5,-6.5,6.5, z_base-0.1, z_top)
    return ring.fuse(core).removeSplitter()
house = housing(zc0+CAP_T, zc0+CAP_T+HOUSE_H)
cap = cap.fuse(house)
cav_top = zc0 + CELL_T + FOOT_BLK[2] + 0.4 + 0.5           # ceiling above the foot block (0.5 headroom)
cap = cap.cut(rbox(-CAV_S/2, CAV_S/2, -CAV_S/2, CAV_S/2, zc0-1, zc0+CAP_T+HOUSE_H-1.5, CAV_R))
cap = cap.cut(cyl(HOLE_D/2, 0, 0, zc0, zc0+CAP_T+HOUSE_H+1))
for sx in (1,-1):                                                                # wire wedges under the plate
    w = Part.Face(Part.makePolygon([V(sx*CAV_S/2,-RAMP_HY,zc0-0.01), V(sx*RAMP_X1,-RAMP_HY,zc0-0.01), V(sx*CAV_S/2,-RAMP_HY,zc0+RAMP_Z), V(sx*CAV_S/2,-RAMP_HY,zc0-0.01)])).extrude(V(0,2*RAMP_HY,0))
    cap = cap.cut(w)
for x,y in SCREW:
    cap = cap.fuse(cyl(BOSS_D/2, x, y, CLR+0.1, zc0+0.01))                        # boss down to CLR above the plate top... see note
for x,y in SCREW:
    cap = cap.cut(cyl(SHANK/2, x, y, -1, zc0+CAP_T+1))
    cap = cap.cut(cyl(HEAD/2, x, y, CLR+0.1+1.3, zc0+CAP_T+1))                    # head floor 1.3 above the boss bottom
cap = cap.removeSplitter()
mouth = [e for e in cap.Edges if isinstance(e.Curve, Part.Circle) and abs(e.Curve.Radius-HEAD/2)<0.01 and abs(e.BoundBox.ZMin-(zc0+CAP_T))<1e-6]
try: cap = cap.makeFillet(1.0, mouth)                 # rounded recess mouth (R1 reproduces the reference volume)
except Exception as ex: print("mouth fillet skipped:", ex)

# ---------------- SHIMS (between MDF and base) ----------------
shims = {}
for t in SHIMS:
    s = rbox(-L/2, L/2, -W/2, W/2, -PLATE-t, -PLATE, R)
    s = s.cut(box(EXIT_X0, L/2+1, -EXIT_HY, EXIT_HY, -PLATE-t-1, 0))
    for x,y in SCREW: s = s.cut(cyl(SHANK/2, x, y, -PLATE-t-1, 0))
    shims[t] = s

# ---------------- references ----------------
metal = rbox(CELL_X0, CELL_X1, -CELL_S/2, CELL_S/2, PLAT_H, PLAT_H+CELL_T, CELL_R).cut(rbox(WIN_X0, WIN_X1, -WIN_HY, WIN_HY, 0, 5, WIN_R))
zf = PLAT_H+CELL_T
foot = box(-FOOT_BLK[0]/2, FOOT_BLK[0]/2, -FOOT_BLK[1]/2, FOOT_BLK[1]/2, zf, zf+FOOT_BLK[2]).fuse(cyl(BUTTON_D/2, 0, 0, zf+FOOT_BLK[2], zf+FOOT_BLK[2]+BUTTON_H))

def add(name, shape, color, transp=0, vis=True):
    o = doc.addObject("Part::Feature", name); o.Shape = shape
    if App.GuiUp: o.ViewObject.ShapeColor = color; o.ViewObject.Transparency = transp; o.ViewObject.Visibility = vis
    return o
add("Base", base, (0.93,0.92,0.88)); add("Cap", cap, (0.93,0.92,0.88))
for t,s in shims.items(): add("Shim_%s" % str(t).replace('.','_'), s, (0.7,0.7,0.75), vis=False)
add("CellMetal_ref", metal, (0.75,0.75,0.78)); add("CellFoot_ref", foot, (0.1,0.1,0.1))
doc.recompute()
PARTS = ["Base","Cap"] + ["Shim_%s" % str(t).replace('.','_') for t in SHIMS]
for nm in PARTS:
    s = doc.getObject(nm).Shape; bb = s.BoundBox
    print(nm, "valid:", s.isValid(), "solids:", len(s.Solids), "vol:", round(s.Volume,1), "z:", round(bb.ZMin,2), "..", round(bb.ZMax,2))
for a,b in (("Base","Cap"),("Base","CellMetal_ref"),("Cap","CellMetal_ref"),("Cap","CellFoot_ref"),("Base","CellFoot_ref"),("Base",PARTS[2])):
    v = doc.getObject(a).Shape.common(doc.getObject(b).Shape).Volume
    if v>1e-6: print("OVERLAP", a, b, round(v,3))
def dist(a,b): return round(doc.getObject(a).Shape.distToShape(doc.getObject(b).Shape)[0],3)
print("gaps: base-cap", dist("Base","Cap"), " base-metal", dist("Base","CellMetal_ref"), " cap-metal", dist("Cap","CellMetal_ref"), " cap-foot", dist("Cap","CellFoot_ref"))
print("cap volume", round(doc.getObject("Cap").Shape.Volume,1), "(ref 4425.7)  base", round(doc.getObject("Base").Shape.Volume,1), "(ref 5664.0)")
print("shell height (base bottom to cap top):", round(doc.getObject("Cap").Shape.BoundBox.ZMax + PLATE, 2), " foot protrudes", round(doc.getObject("CellFoot_ref").Shape.BoundBox.ZMax - doc.getObject("Cap").Shape.BoundBox.ZMax,2))
if App.GuiUp: Gui.SendMsgToActiveView("ViewFit")

# ---- outputs next to this script: <part>.stl (print) + .step, and the FreeCAD document (skipped when the caller
# seeds the namespace with EXPORT = False, e.g. assembly.py previewing)
import os as _os
if globals().get('EXPORT', True):
    _CAD = _os.path.dirname(_os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'
    for _nm in PARTS:
        export_stl(doc.getObject(_nm).Shape, _os.path.join(_CAD, 'foot_%s.stl' % _nm.lower()))
        doc.getObject(_nm).Shape.exportStep(_os.path.join(_CAD, 'foot_%s.step' % _nm.lower()))
    doc.saveAs(_os.path.join(_CAD, 'foot.FCStd'))
