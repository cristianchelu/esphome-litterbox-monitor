import FreeCAD as App, FreeCADGui as Gui, Part, math, os
from FreeCAD import Vector as V, Placement, Rotation

# Whole monitor: 750 x 580 x 18 KOMPLEMENT underside, four load-cell feet at the corners, brain shell on the front edge.
# Frame = the shell's: X along the front edge (centred), +Y into the board, Z up, MDF top at Z = 0.
MDF_W, MDF_D, MDF_T = 750.0, 580.0, 18.0
FOOT_INSET_X = 60.0      # foot centre in from the short (580) edges, i.e. along the long side
FOOT_INSET_Y = 40.0      # foot centre in from the long (750) edges
CAD = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor/tools/cad'
EXPORT = globals().get('EXPORT', True)   # False: preview only, no STL/STEP/FCStd written by this or the part scripts

def run(name):
    ns = {'EXPORT': EXPORT, '__file__': os.path.join(CAD, name)}   # so the part scripts export next to themselves
    exec(open(os.path.join(CAD, name)).read(), ns)
    return ns
nf = run('foot.py'); nb = run('brain_shell.py'); nh = run('hx711.py'); nc = run('channels.py')

for d in list(App.listDocuments()):
    if d == "LitterboxMonitor": App.closeDocument(d)
doc = App.newDocument("LitterboxMonitor")
def add(name, shape, color, transp=0, pl=None):
    o = doc.addObject("Part::Feature", name); o.Shape = shape
    if pl: o.Placement = pl
    if App.GuiUp: o.ViewObject.ShapeColor = color; o.ViewObject.Transparency = transp
    return o

add("MDF", Part.makeBox(MDF_W, MDF_D, MDF_T, V(-MDF_W/2, 0, -MDF_T)), (0.55,0.45,0.30), 60)
for nm in ("Top","Mid","Sleeve","TailSleeve","CapSleeve","Cap","ESP32_ref","TTP223_ref"):
    o = nb['doc'].getObject(nm); add("Shell_"+nm, o.Shape, o.ViewObject.ShapeColor if App.GuiUp else (0.9,0.9,0.9))

# HX711 shell at the board centre, hung from the underside like the feet
hx_c = V(0, MDF_D/2, 0); hxL, hxW, hxR = nh['L'], nh['W'], nh['R']
pl = Placement(V(hx_c.x, hx_c.y, -MDF_T - nh['PLATE']), Rotation(V(1,0,0), 180))
for nm,col in (("Tray",(0.93,0.92,0.88)),("Cap",(0.93,0.92,0.88)),("HX711_ref",(0.8,0.1,0.1))):
    add("HX_"+nm, nh['doc'].getObject(nm).Shape, col, pl=pl)
def hx_corner_entry(toward):
    """point on the HX tray's corner arc nearest the direction 'toward' (world), where the channel ducks under the wall"""
    cx = hx_c.x + math.copysign(hxL/2-hxR, toward.x-hx_c.x); cy = hx_c.y + math.copysign(hxW/2-hxR, toward.y-hx_c.y)
    u = V(toward.x-cx, toward.y-cy, 0).normalize()
    return V(cx + u.x*hxR, cy + u.y*hxR, -MDF_T)

# feet: local +Z is toward the floor and local +X is the wire notch; flip about X, spin so +X points straight at the
# foot's HX711 corner entry (the channel run is straight, so the endcap's nose enters the notch square), then drop
# the base plate underside (local Z = -PLATE) onto the MDF underside
FEET = [(sx*(MDF_W/2-FOOT_INSET_X), y) for sx in (-1,1) for y in (FOOT_INSET_Y, MDF_D-FOOT_INSET_Y)]
runs = []
for i,(fx,fy) in enumerate(FEET):
    p1 = hx_corner_entry(V(fx,fy,0))
    u = V(p1.x-fx, p1.y-fy, 0).normalize(); ang = math.degrees(math.atan2(u.y, u.x))
    pl = Placement(V(fx, fy, -MDF_T - nf['PLATE']), Rotation(V(0,0,1), ang).multiply(Rotation(V(1,0,0), 180)))
    for nm,col in (("Base",(0.93,0.92,0.88)),("Cap",(0.93,0.92,0.88)),("CellMetal_ref",(0.75,0.75,0.78)),("CellFoot_ref",(0.1,0.1,0.1))):
        add("Foot%d_%s" % (i+1, nm), nf['doc'].getObject(nm).Shape, col, pl=pl)
    p0 = V(fx + u.x*nf['L']/2, fy + u.y*nf['L']/2, -MDF_T)                    # notch on the foot's outer face
    runs.append(("foot%d" % (i+1), nc['run'](nc['CELL'], p0, p1)))
# ---- wire channels (channels.py): four foot -> HX711 corner runs (CELL profile) and the HX711 -> brain run (RIBBON), each a straight bar
# whose ends go through the enclosures' notches. HX711 ribbon exit (tray local +Y end -> world -Y side, local X = world X)
# straight to the brain's rear-wall notch
hx_exit = V(nh['RIBBON_X'], hx_c.y - hxW/2, -MDF_T)
brain_slot = V(nb['RIB_XC'], nb['T'], -MDF_T)
if abs(hx_exit.x - brain_slot.x) > 1e-6: print("HX711 ribbon exit X", hx_exit.x, "!= brain slot X", brain_slot.x, "-> the run is not straight")
runs.append(("hx_brain", nc['run'](nc['RIBBON'], hx_exit, brain_slot)))
for name, secs in runs:
    for j,(sh,pl,l) in enumerate(secs): add("Chan_%s_%d" % (name, j+1), sh, (0.55,0.6,0.7), pl=pl)
    print("run", name, ": sections", [round(l,1) for _,_,l in secs])
doc.recompute()
z_floor = doc.getObject("Foot1_CellFoot_ref").Shape.BoundBox.ZMin
z_shell = doc.getObject("Shell_Cap").Shape.BoundBox.ZMin
print("feet at:", [(round(x,1), round(y,1)) for x,y in FEET], " each aimed at its HX711 corner entry")
print("floor at Z", round(z_floor,2), " shell lowest Z", round(z_shell,2), " -> ground clearance under the shell", round(z_shell - z_floor,2), "mm")
print("HX711 shell lowest Z", round(doc.getObject("HX_Cap").Shape.BoundBox.ZMin,2), " -> clearance", round(doc.getObject("HX_Cap").Shape.BoundBox.ZMin - z_floor,2), "mm")
for i in range(4):
    for a,b in (("Foot%d_Base"%(i+1),"MDF"),("Foot%d_Cap"%(i+1),"MDF")):
        v = doc.getObject(a).Shape.common(doc.getObject(b).Shape).Volume
        if v>1e-6: print("OVERLAP", a, b, round(v,3))
# channels vs the shells and feet: the bar ends must pass through the notches without touching
solids = ["Shell_Mid","Shell_TailSleeve","HX_Tray","HX_Cap","MDF"] + ["Foot%d_%s" % (i+1, p) for i in range(4) for p in ("Base","Cap")]
for o in doc.Objects:
    if o.Name.startswith("Chan_"):
        for other in solids:
            v = o.Shape.common(doc.getObject(other).Shape).Volume
            if v>1e-6: print("OVERLAP", o.Name, other, round(v,2))
chan = [o for o in doc.Objects if o.Name.startswith("Chan_")]
tight = min(((a.Shape.distToShape(b.Shape)[0], a.Name, b.Name) for i,a in enumerate(chan) for b in chan[i+1:]
             if a.Name.split("_")[1] != b.Name.split("_")[1]), key=lambda t: t[0])
print("closest parts of different runs:", tight[1], tight[2], round(tight[0],2), "mm")
for name, secs in runs:
    tgt = {"hx_brain": ("HX_Tray", "Shell_Mid")}.get(name, ("Foot%s_Base" % name[-1], "HX_Tray"))
    for (sh,pl,l), t in zip((secs[0], secs[-1]), tgt):
        s = sh.copy(); s.Placement = pl
        print("  run %s end in %s: clearance %.2f" % (name, t, doc.getObject(t).Shape.distToShape(s)[0]))
# print files: one section set per profile (the four foot runs are identical)
if EXPORT:
    for name, secs in runs:
        if name in ("foot2","foot3","foot4"): continue
        prof = "cell" if name.startswith("foot") else "ribbon"
        for j,(sh,pl,l) in enumerate(secs):
            nc['export_print'](sh, os.path.join(CAD, "channel_%s_%dof%d_%dmm.stl" % (prof, j+1, len(secs), round(l))))
    doc.saveAs(os.path.join(CAD, 'assembly.FCStd'))
if App.GuiUp: Gui.SendMsgToActiveView("ViewFit")
