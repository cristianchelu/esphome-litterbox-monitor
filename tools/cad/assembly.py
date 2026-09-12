import FreeCAD as App, FreeCADGui as Gui, Part, math, os
from FreeCAD import Vector as V, Placement, Rotation

# Whole monitor: 750 x 580 x 18 KOMPLEMENT underside, four load-cell feet at the corners, brain shell on the front edge.
# Frame = the shell's: X along the front edge (centred), +Y into the board, Z up, MDF top at Z = 0.
MDF_W, MDF_D, MDF_T = 750.0, 580.0, 18.0
FOOT_INSET_X = 60.0      # foot centre in from the short (580) edges, i.e. along the long side
FOOT_INSET_Y = 40.0      # foot centre in from the long (750) edges
CAD = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'

def run(name):
    ns = {}
    exec(open(os.path.join(CAD, name)).read(), ns)
    return ns
nf = run('foot.py'); nb = run('brain_shell.py'); nh = run('hx711.py')

for d in list(App.listDocuments()):
    if d == "LitterboxMonitor": App.closeDocument(d)
doc = App.newDocument("LitterboxMonitor")
def add(name, shape, color, transp=0, pl=None):
    o = doc.addObject("Part::Feature", name); o.Shape = shape
    if pl: o.Placement = pl
    o.ViewObject.ShapeColor = color; o.ViewObject.Transparency = transp; return o

add("MDF", Part.makeBox(MDF_W, MDF_D, MDF_T, V(-MDF_W/2, 0, -MDF_T)), (0.55,0.45,0.30), 60)
for nm in ("Top","Mid","Sleeve","TailSleeve","CapSleeve","Cap","ESP32_ref","TTP223_ref"):
    o = nb['doc'].getObject(nm); add("Shell_"+nm, o.Shape, o.ViewObject.ShapeColor)

# feet: local +Z is toward the floor and local +X is the wire exit; flip about X, spin so +X points at the board centre,
# then drop the base plate underside (local Z = -PLATE) onto the MDF underside
centre = V(0, MDF_D/2, 0)
FEET = [(sx*(MDF_W/2-FOOT_INSET_X), y) for sx in (-1,1) for y in (FOOT_INSET_Y, MDF_D-FOOT_INSET_Y)]
for i,(fx,fy) in enumerate(FEET):
    ang = math.degrees(math.atan2(centre.y-fy, centre.x-fx))
    pl = Placement(V(fx, fy, -MDF_T - nf['PLATE']), Rotation(V(0,0,1), ang).multiply(Rotation(V(1,0,0), 180)))
    for nm,col in (("Base",(0.93,0.92,0.88)),("Cap",(0.93,0.92,0.88)),("CellMetal_ref",(0.75,0.75,0.78)),("CellFoot_ref",(0.1,0.1,0.1))):
        add("Foot%d_%s" % (i+1, nm), nf['doc'].getObject(nm).Shape, col, pl=pl)
# HX711 shell at the board centre, hung from the underside like the feet
pl = Placement(V(0, MDF_D/2, -MDF_T - nh['PLATE']), Rotation(V(1,0,0), 180))
for nm,col in (("Tray",(0.93,0.92,0.88)),("Cap",(0.93,0.92,0.88)),("HX711_ref",(0.8,0.1,0.1)),("Dupont_ref",(0.85,0.75,0.1))):
    add("HX_"+nm, nh['doc'].getObject(nm).Shape, col, pl=pl)
# ---- cable channels (channels.py): four foot -> HX711 corner runs, HX711 -> brain ribbon run, a USB lead stub
nc = run('channels.py')
def foot_exit(fx, fy):
    u = V(centre.x-fx, centre.y-fy, 0).normalize()
    return V(fx + u.x*nf['L']/2, fy + u.y*nf['L']/2, -MDF_T), u
hx_c = V(0, MDF_D/2, 0); hxL, hxW, hxR = nh['L'], nh['W'], nh['R']
def hx_corner_entry(toward):
    """point on the HX tray's corner arc nearest the direction 'toward' (world), where the cable ducks under the wall"""
    cx = hx_c.x + math.copysign(hxL/2-hxR, toward.x-hx_c.x); cy = hx_c.y + math.copysign(hxW/2-hxR, toward.y-hx_c.y)
    u = V(toward.x-cx, toward.y-cy, 0).normalize()
    return V(cx + u.x*hxR, cy + u.y*hxR, -MDF_T)
runs = []
for i,(fx,fy) in enumerate(FEET):
    p0, u = foot_exit(fx, fy); p1 = hx_corner_entry(V(fx,fy,0))
    kink = math.degrees(math.acos(max(-1,min(1, u.dot(V(p1.x-p0.x, p1.y-p0.y, 0).normalize())))))
    runs.append(("foot%d" % (i+1), nc['run']("ribbon", p0, p1), kink))
# HX711 ribbon exit (tray local +Y end -> world -Y side, local X = world X) straight to the brain's roof slot
hx_exit = V(nh['RIBBON_X'], hx_c.y - hxW/2, -MDF_T)
brain_slot = V(nb['RIB_XC'], nb['T'], -MDF_T)
runs.append(("hx_brain", nc['run']("ribbon", hx_exit, brain_slot), 0.0))
for name, secs, kink in runs:
    for j,(sh,pl,l) in enumerate(secs):
        add("Chan_%s_%d" % (name, j+1), sh, (0.55,0.6,0.7), pl=pl)
    print("run", name, ": sections", [round(l,1) for _,_,l in secs], " kink at start %.1f deg" % kink)
doc.recompute()
z_floor = min(doc.getObject("Foot1_CellFoot_ref").Shape.BoundBox.ZMin for i in range(1))
z_shell = doc.getObject("Shell_Cap").Shape.BoundBox.ZMin
print("feet at:", [(round(x,1), round(y,1)) for x,y in FEET], " pointing at the board centre")
print("floor at Z", round(z_floor,2), " shell lowest Z", round(z_shell,2), " -> ground clearance under the shell", round(z_shell - z_floor,2), "mm")
print("HX711 shell lowest Z", round(doc.getObject("HX_Cap").Shape.BoundBox.ZMin,2), " -> clearance", round(doc.getObject("HX_Cap").Shape.BoundBox.ZMin - z_floor,2), "mm")
for i in range(4):
    for a,b in (("Foot%d_Base"%(i+1),"MDF"),("Foot%d_Cap"%(i+1),"MDF")):
        v = doc.getObject(a).Shape.common(doc.getObject(b).Shape).Volume
        if v>1e-6: print("OVERLAP", a, b, round(v,3))
# print files: one set per distinct run geometry (the four foot runs are identical)
for name, secs, _ in runs:
    if name in ("foot2","foot3","foot4"): continue
    for j,(sh,pl,l) in enumerate(secs):
        nc['export_print'](sh, os.path.join(CAD, "channel_%s_%dof%d_%dmm.stl" % (name.replace("foot1","foot"), j+1, len(secs), round(l))))
# channel vs shells/feet interference
for o in doc.Objects:
    if o.Name.startswith("Chan_"):
        for other in ("Shell_Mid","HX_Tray","Foot1_Base","Foot2_Base","Foot3_Base","Foot4_Base"):
            v = o.Shape.common(doc.getObject(other).Shape).Volume
            if v>1e-6: print("OVERLAP", o.Name, other, round(v,2))
doc.saveAs(os.path.join(CAD, 'assembly.FCStd'))
Gui.SendMsgToActiveView("ViewFit")
