import FreeCAD as App, FreeCADGui as Gui, Part, math
from FreeCAD import Vector as V

# ---- coordinates: X along shelf edge (centred), +Y goes under the MDF, Z up, MDF top = 0
MDF_T   = 18.0
W       = 78.0          # width along the edge: flat rear wall must span ribbon slot and USB notch
R_OUT   = 15.0          # plan-view corner radius at the nose
R_REAR  = 10.0          # tail corners: tighter, so the screw bosses fit inside the short tail's liner
N_TOP   = 8.0           # nose depth at the top (in front of edge)
N_BOT   = 23.0          # nose depth at the bottom
Z_CORNER= -16.0         # slope ends 2 mm above the MDF bottom plane; vertical skirt below
Z_SPLIT = -MDF_T        # white shell splits into Top (nose above) and Mid (skirt + tail) here
ROOF    = 1.0           # tail roof against the MDF underside
WALL    = 1.2           # all shell walls
PAD_WALL= 0.9           # white wall left at the centre of the touch dish (dish depth = WALL - PAD_WALL)
DISK_D  = 10.0          # touch-target dish on the outer face, centred on the pad's circle: a shallow spherical
                        # cap, so it fades into the face instead of leaving a step
EDGE_R  = 2.0           # round-over on the Top's convex outer edges
BAR_WALL= 0.8           # white wall left at the light bar
BACK    = 1.2           # nose back wall (against MDF edge)
NOSE_ROOF = 1.2
CLR     = 0.1           # minimum clearance between any two mating surfaces
GAP     = CLR           # sleeve/base clearance
SW      = 0.9           # liner walls (two 0.42 perimeters of black is opaque)
SW_ROOF = 0.8           # tail liner roof under the Mid roof, four layers
SW_PAD  = 0.4           # sleeve skin left in front of the touch pad (uninterrupted, pad taped behind it)
CSW     = 0.6           # cap sleeve: black plate lying on the cap, three layers
CAP     = 1.2
LIP_H   = 2.0           # glue lip: inner 0.5 of the Top wall drops into a 0.7 rebate in the Mid skirt
LIP_T   = 0.5
# ESP32-S3 SuperMini 23.5 x 18 x 1.2, components UP so the WS2812 lights the nose cavity; USB-C (8.94 x 7.35 x 3.11,
# protrudes 1.5) out the rear, under the board. Seen from above with the USB pointing +Y the wired row (5V GND 3V3 13 12 11
# from the USB end, then 10 9 8) is the +X edge. The board's X is set by the LED: it sits on the light bar's centre line
# (2026-09-13, was -7.7 with the board mirrored about the USB notch: the bar lit visibly lopsided), so the board straddles
# the centre with its wired row 2.5 mm past X = 0; the ribbon slot moves out to the +X flank beside it.
PCB_L, PCB_W = 23.5, 18.0
# through-hole grid (measured 2026-09-12): 2 rows x 9, 2.54 pitch, rows 1.27 in from the long edges, ends 1.59
PIN_PITCH, PIN_INSET, PIN_END, PIN_N, PIN_HOLE = 2.54, 1.27, 1.59, 9, 1.0
# WS2812 sits between the GPIO9 and GPIO10 pads (8th/7th pin from the USB end, wired row), just inboard of them. It has
# to be in front of the sleeve's roof edge (Y = -BACK-GAP) to shine up into the nose: that fixes the board's Y and T.
LED_X, LED_Y, LED_FROM_EDGE, LED_S, LED_H = 0.0, -3.5, 2.5, 2.0, 1.0   # LED on the bar's centre line
PCB_X1 = LED_X + LED_FROM_EDGE        # inner edge (wired row) .. outer edge (unwired row)
PCB_X0 = PCB_X1 - PCB_W
PCB_XC = (PCB_X0+PCB_X1)/2            # USB notch here
PIN_X_OUT, PIN_X_IN = PCB_X0+PIN_INSET, PCB_X1-PIN_INSET
PCB_Y1 = LED_Y + PIN_END + 6.5*PIN_PITCH
PCB_Y0 = PCB_Y1 - PCB_L
PIN_Y  = [PCB_Y1-PIN_END-i*PIN_PITCH for i in range(PIN_N)]   # pin 1 at the USB end
# retention is pegs only (rev 4): the board sits on standoffs at pins 4 and 6 of both rows, a peg through each pad hole.
# Nothing springs; the CapSleeve captures the board once it is on, and the stack is built roof-down so gravity holds it
# until then. The rev 3 snap posts (0.8 thick, 1.0 deflection 4.6 from the root, ~6% strain across layers) broke at once.
PEG_PINS = (3, 5)                     # 0-based from the USB end: pins 4 and 6, both rows bare from pin 4 back
PEG_D, PEG_H = 0.9, 1.2               # 0.05 per side in the 1.0 hole (measure a print), flush with the board underside
ROOF_Z  = -MDF_T - ROOF               # Mid roof underside
SROOF_T = ROOF_Z - GAP                # sleeve roof top ..
SROOF_B = SROOF_T - SW_ROOF           # .. and underside: the ESP32 hangs from here
USB_HT, USB_CLR = 3.11, 0.3           # port shell height, air between it and the tail liner roof
USB_ZT  = SROOF_B - USB_CLR           # the stack hangs from the liner roof; the port ends up 0.7 higher than in rev 1
PCB_ZT  = USB_ZT - USB_HT
PCB_ZB  = PCB_ZT - 1.2
USB_ZC  = (PCB_ZT + USB_ZT)/2
PLATE_T = PCB_ZB - 0.8                # cap sleeve top: pad-side passives (0.7, facing down now) + 0.1
PLATE_B = PLATE_T - CSW
Z_BOT   = PLATE_B - GAP               # base underside / cap top
CAP_BOT = Z_BOT - CAP
T       = PCB_Y1 + CLR + WALL         # PCB end + clearance + Mid rear wall (port stub ends 0.2 proud); the sleeve's rear wall
                                      # is slotted for the board, so the plug still reaches the port
SCREW_XY = [(-30,7),(30,7)]           # two bosses on the flanks, inside the tail liner's rear corners
BOSS_R   = 5.0
# Leads (2026-09-13, the printed pin header + Dupont housing are gone: Cristian doesn't unplug it): everything is
# soldered flat onto the pads and leaves them horizontally. HX711 5V/GND/3V3 off the wired row's pads 1-3, out through
# the ribbon slot in the MDF-facing roof (same 14.6 x 4 footprint as rev 4, on the +X flank); HX711 CLK/DAT off the
# outer row's pads 2-3; touch OUT off the outer row's pad 1, its VCC and GND second wires on the 3V3 and GND pads.
# Nothing printed holds the leads: they are dressed by hand and taped down (2026-09-14, the wire combs and modelled
# routes are gone), so the tail liner's underside is clear from the standoffs to the flanks.
RIB_X0   = PCB_X1 + 2.0               # slot from 1 mm outboard of the pin-4/6 standoffs (they reach PCB_X1 + 1) ...
RIB_X1   = SCREW_XY[1][0] - BOSS_R - 2.3   # ... to 2.3 short of the +X boss: 18.2 wide, takes the 16 mm RIBBON channel bar
RIB_XC   = (RIB_X0+RIB_X1)/2          # 13.6: hx711.py RIBBON_X must match so the run is straight
RIB_DEPTH = 4.5                       # slot depth in front of the rear wall: the bar ends 0.7 short of its front edge
NOTCH_H  = 2.9                        # channels.py RIBBON notch_h: notch over the rear wall for the bar (was just the roof's 1 mm)
# TTP223B 15 x 11, the 3.5 mm pin strip taken off the 15 mm length (pins along the short edge). PCB lies on its
# side: 15 mm across the face (X), 11 mm along the slope, pin strip at -X. Circle centre is 9.25 from the pin
# edge -> PCB X -9.25..5.75 puts it on X = 0; along the slope the circle is the PCB centre.
PAD_L, PAD_W, PAD_PINS = 15.0, 11.0, 3.5
PAD_X0 = -(PAD_PINS + (PAD_L-PAD_PINS)/2); PAD_X1 = PAD_X0 + PAD_L
PAD_V0 = 1.7                                  # pin-free top edge just under the nose roof
PAD_V1 = PAD_V0 + PAD_W
PAD_CIRCLE_V = (PAD_V0+PAD_V1)/2
BAR_H = 3.0                            # bar centred between the pad and the skirt corner (set after SLOPE_LEN)
BAR_HW = 20.0                         # light bar half width

for d in list(App.listDocuments()):
    if d == "LitterboxBrainShell": App.closeDocument(d)
doc = App.newDocument("LitterboxBrainShell")

def export_stl(shape, path):
    import MeshPart
    MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.05, AngularDeflection=0.35, Relative=False).write(path)
def box(x0,x1,y0,y1,z0,z1): return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))
def cyl(r,x,y,z0,z1): return Part.makeCylinder(r, z1-z0, V(x,y,z0))
def rbox(x0,x1,y0,y1,z0,z1,r,front=True,back=True,r_back=None):
    """box with vertical edges filleted: 'front' = the y0 corners (radius r), 'back' = the y1 corners (r_back, default r)"""
    b = box(x0,x1,y0,y1,z0,z1)
    for y, rad, on in ((y0, r, front), (y1, r if r_back is None else r_back, back)):
        if not on or rad <= 0: continue
        es = [e for e in b.Edges if abs(e.tangentAt(e.FirstParameter).z) > 0.999
              and abs(e.Vertexes[0].Point.y-y) < 1e-6 and min(abs(e.Vertexes[0].Point.x-x0), abs(e.Vertexes[0].Point.x-x1)) < 1e-6]
        if es: b = b.makeFillet(rad, es)
    return b
def rb_full(t, z0, z1):   # the shell's plan outline inset t (nose R_OUT, tail R_REAR), rear face at T-t
    return rbox(-W/2+t, W/2-t, -N_BOT+t, T-t, z0, z1, R_OUT-t, r_back=R_REAR-t)
def rb_nose(t, y1, z0, z1):
    return rbox(-W/2+t, W/2-t, -N_BOT+t, y1, z0, z1, R_OUT-t, back=False)

# slope frame: origin at outer slope top corner, v along slope (down-front), w inward
ang = math.degrees(math.atan2(N_BOT-N_TOP, -Z_CORNER))
sv = V(0,-math.sin(math.radians(ang)),-math.cos(math.radians(ang)))
sw = V(0,-sv.z, sv.y)
SLOPE_LEN = math.hypot(N_BOT-N_TOP, Z_CORNER)
BAR_VC = (PAD_V1 + SLOPE_LEN)/2
BAR_V0, BAR_V1 = BAR_VC-BAR_H/2, BAR_VC+BAR_H/2
def sbox(x0,x1,v0,v1,w0,w1):
    b = Part.makeBox(x1-x0, v1-v0, w1-w0, V(x0,v0,w0))
    m = App.Matrix(); m.A11,m.A12,m.A13=1,0,0; m.A21,m.A22,m.A23=0,sv.y,sw.y; m.A31,m.A32,m.A33=0,sv.z,sw.z
    b.transformShape(m); b.translate(V(0,-N_TOP,0)); return b       # rigid: faces stay planes, so they fillet cleanly
def spt(x, v, w):    # slope-frame point -> world
    return V(x,-N_TOP,0) + sv*v + sw*w
def sstadium(x0,x1,v0,v1,w0,w1):   # rounded-end slot in the slope frame, full radius on the v extent
    r = (v1-v0)/2; vc = (v0+v1)/2
    sh = sbox(x0+r, x1-r, v0, v1, w0, w1)
    for x in (x0+r, x1-r):
        sh = sh.fuse(Part.makeCylinder(r, w1-w0, spt(x, vc, w0), sw))
    return sh
def outside_slope(w):  # half-space in front of the slope plane offset w inward
    return sbox(-200,200, -200,200, -300, w)
def stadium_y(xc, zc, w, h, y0, y1):
    r = h/2
    sh = box(xc-w/2+r, xc+w/2-r, y0, y1, zc-r, zc+r)
    for sx in (-1,1):
        sh = sh.fuse(Part.makeCylinder(r, y1-y0, V(xc+sx*(w/2-r), y0, zc), V(0,1,0)))
    return sh
# USB-C port: stadium-shaped hole, split at its centre line. Mid and sleeve carry the upper half plus a wider rectangular
# notch below it (the board goes up into place with the port stub in the notch); Cap and CapSleeve carry blocks that
# fill their notch and form the lower rounded corners.
USB_W, USB_H = 8.94+0.5, USB_HT+0.5
USB_HORN = 1.2                          # shoulder each side of the stadium that the blocks fill
def port_opening(shape):
    shape = shape.cut(stadium_y(PCB_XC, USB_ZC, USB_W, USB_H, PCB_Y1-1, T+1))
    return shape.cut(box(PCB_XC-USB_W/2-USB_HORN, PCB_XC+USB_W/2+USB_HORN, PCB_Y1-1, T+1, Z_BOT-1, USB_ZC))
def port_block(y0, y1, z0):             # fills the notch between y0..y1 from z0 up to the port's centre line
    b = box(PCB_XC-USB_W/2-USB_HORN+CLR, PCB_XC+USB_W/2+USB_HORN-CLR, y0, y1, z0, USB_ZC-CLR)
    return b.cut(stadium_y(PCB_XC, USB_ZC, USB_W, USB_H, y0-1, y1+1))

# ---------------- white shell (built whole, then split) ----------------
outer = rb_full(0, Z_BOT, 0)
outer = outer.cut(outside_slope(0)).cut(box(-W, W, 0, T+1, -MDF_T, 1))          # slope face, MDF notch
i = WALL
nose_cav = rb_nose(i, -BACK, Z_BOT-5, -NOSE_ROOF).cut(outside_slope(WALL))
tail_cav = rbox(-W/2+i, W/2-i, -BACK-1, T-WALL, Z_BOT-5, ROOF_Z, R_OUT-i, front=False, r_back=R_REAR-i)
base = outer.cut(nose_cav).cut(tail_cav)
disk_c = V(0,-N_TOP,0) + sv*PAD_CIRCLE_V
DISK_DEPTH = WALL - PAD_WALL
R_DISH = (DISK_D**2/4 + DISK_DEPTH**2)/(2*DISK_DEPTH)                       # sphere through the rim circle and the centre depth
base = base.cut(Part.makeSphere(R_DISH, disk_c - sw*(R_DISH - DISK_DEPTH)))   # touch dish
base = base.cut(sstadium(-BAR_HW-0.3,BAR_HW+0.3, BAR_V0-0.3,BAR_V1+0.3, BAR_WALL, WALL+0.6))    # light bar thinned, 0.3 beyond the slot
base = port_opening(base)
base = base.cut(box(RIB_X0, RIB_X1, T-WALL-RIB_DEPTH, T+1, -MDF_T-NOTCH_H, -MDF_T+0.1))   # ribbon slot through the roof, NOTCH_H notch over the rear wall
for x,y in SCREW_XY: base = base.cut(cyl(3.9/2, x, y, CAP_BOT-1, 0))
base = base.removeSplitter()

top = base.common(box(-100,100,-100,100, Z_SPLIT, 10))
mid = base.common(box(-100,100,-100,100, -100, Z_SPLIT))
# glue lip: Top keeps its inner LIP_T and drops LIP_H-CLR into the Mid; Mid rebated LIP_T+CLR deep, LIP_H tall
def ring(t_out, t_in):   # plan ring between insets t_out and t_in of the nose outline
    return rb_nose(t_out, 0, -100, 100).cut(rb_nose(t_in, 1, -101, 101))
def ring_full(t_out, t_in):
    return rb_full(t_out, -100, 100).cut(rb_full(t_in, -101, 101))
lip    = ring(WALL-LIP_T, WALL).common(box(-W,W,-N_BOT-1,-BACK, Z_SPLIT-LIP_H+CLR, Z_SPLIT+0.01))
rebate = ring(WALL-LIP_T-CLR, WALL+0.2).common(box(-W, W, -N_BOT-1, -BACK, Z_SPLIT-LIP_H, Z_SPLIT+1))
# same joint at the Mid/Cap seam: Mid loses its inner LIP_T+CLR for LIP_H at the bottom, Cap grows the mating rim
t_rb = WALL-LIP_T-CLR
rebate_cap = ring_full(t_rb, WALL+0.2).common(box(-W, W, -N_BOT-1, T+1, Z_BOT-1, Z_BOT+LIP_H))   # wall only, never the interior
# round the Top's convex outer edges: top/slope, top/sides, the slope's run-outs into the corner cylinders, slope/skirt.
# Two passes: OCC refuses the front edge in the same call as any other (the vertex where side plane, corner cylinder,
# top and slope meet), so it goes first and the rest - including the new fillet's end edges - blend into it.
def outer_edges(sh, min_deg=10.0):
    """convex outer edges: not on the bottom or the rear face, clear of the cavity, with a real dihedral angle (skips
    tangent seams and the touch dish's rim)"""
    out=[]
    for e in sh.Edges:
        bb=e.BoundBox
        if bb.ZMax < Z_SPLIT+0.5 or bb.YMin > -1e-6: continue
        pm = e.valueAt(e.FirstParameter + 0.5*(e.LastParameter-e.FirstParameter))
        if nose_cav.distToShape(Part.Vertex(pm))[0] < 0.6: continue
        faces = [f for f in sh.Faces if any(fe.isSame(e) for fe in f.Edges)]
        if len(faces) != 2: continue
        ns = []
        for f in faces:
            u,v = f.Surface.parameter(pm); ns.append(f.normalAt(u,v))
        ang = math.degrees(ns[0].getAngle(ns[1]))
        if min(ang, 180-ang) < min_deg: continue
        out.append(e)
    return out
try:
    front = [e for e in outer_edges(top) if abs(e.BoundBox.ZMax) < 1e-6 and abs(e.BoundBox.YMax+N_TOP) < 1e-6 and abs(e.BoundBox.YMin+N_TOP) < 1e-6]
    top = top.makeFillet(EDGE_R, front)
    top = top.makeFillet(EDGE_R, outer_edges(top))
except Exception as ex: print("Top edge fillet skipped:", ex)
top = top.fuse(lip).removeSplitter()
mid = mid.cut(rebate).cut(rebate_cap).removeSplitter()

# ---------------- SLEEVE (black, nose only — unchanged from rev 1) ----------------
o = WALL+GAP; n = o+SW
so = rb_nose(o, -BACK-GAP,    -100, -NOSE_ROOF-GAP).cut(outside_slope(o))
si = rb_nose(n, -BACK-GAP-SW, -101, -NOSE_ROOF-GAP-SW).cut(outside_slope(n))
sleeve = so.cut(si).common(box(-100,100,-100,10, Z_BOT+CLR, 5))
sleeve = sleeve.cut(sbox(PAD_X0-CLR, PAD_X1+CLR, PAD_V0-CLR, PAD_V1+CLR, WALL+GAP+SW_PAD, 4.0))   # pad recess on the inside, skin stays
sleeve = sleeve.cut(sstadium(-BAR_HW,BAR_HW, BAR_V0,BAR_V1, 1.0,4.0))                  # light bar slot, round ends
sleeve = sleeve.cut(box(-W/2+n, W/2-n, -BACK-GAP-SW-1, -BACK-GAP+1, -40, SROOF_T+CLR))  # back wall open below the tail liner's roof (which laps under it)
sleeve = sleeve.removeSplitter()

# ---------------- TAIL SLEEVE (black): open-bottom box lining the tail, roof under the Mid roof ----------------
# Its outer skin butts CLR behind the nose sleeve's back wall; the joint is lapped so no seam sees light: the roof runs
# on under the nose sleeve's back wall, and thin tongues continue the side walls inside the nose sleeve's walls.
# Below the nose sleeve's back wall the two cavities are one space.
TAIL_Y0 = -BACK-GAP+CLR
TONGUE_L, TONGUE_T = 3.0, 0.6
tail = rb_full(o, Z_BOT+CLR, SROOF_T).cut(rb_full(n, Z_BOT-1, SROOF_B)).common(box(-100,100, TAIL_Y0, 100, -100, 100))
q = n + CLR
tail = tail.fuse(rb_full(q, SROOF_B, SROOF_T).common(box(-100,100, -BACK-GAP-SW-CLR, TAIL_Y0+0.01, -100, 100)))    # roof tongue
tail = tail.fuse(rb_full(q, PLATE_T+CLR, SROOF_T).cut(rb_full(q+TONGUE_T, Z_BOT-1, 100))
                 .common(box(-100,100, TAIL_Y0-TONGUE_L, TAIL_Y0+0.01, -100, 100)))                                  # side tongues, above the CapSleeve
# the board's rear end sits inside the rear wall zone: slot for it (open bottom, the board comes up from below),
# a U above it for the port stub (stadium top, straight sides down to the board). Below the board the CapSleeve's bar fills it.
tail = tail.cut(box(PCB_X0-CLR, PCB_X1+CLR, T-n-1, T+1, Z_BOT-1, PCB_ZT+CLR))
tail = tail.cut(stadium_y(PCB_XC, USB_ZC, USB_W, USB_H, T-n-1, T+1))
tail = tail.cut(box(PCB_XC-USB_W/2, PCB_XC+USB_W/2, T-n-1, T+1, PCB_ZT, USB_ZC))
tail = tail.cut(box(RIB_X0, RIB_X1, T-WALL-RIB_DEPTH, T+1, min(SROOF_B-0.1, -MDF_T-NOTCH_H), SROOF_T+0.1))   # ribbon slot, same footprint as the Mid's, notch to the same depth
for x,y in SCREW_XY: tail = tail.cut(cyl(3.9/2, x, y, SROOF_B-1, SROOF_T+1))
# ---- PCB retention, all on the tail liner's roof: the board goes up from below, port stub into the rear-wall U.
# Wiring assumption (2026-09-12): only 5V/GND/3V3 stay on the inner row (pins 1-3 from the USB end); HX711 CLK/DAT and
# the touch pin move to the outer row's three USB-end pins. From pin 4 back both rows are free, so the retention is
# symmetric: standoffs with pegs on the pin-4 and pin-6 pads, a pad on the port shell, a foot on the chip, and the bare
# underside of the antenna end rests on a bar on the CapSleeve.
def hang(shape):
    global tail; tail = tail.fuse(shape)
SO_W = 1.8
WIRED_Y = PIN_Y[2] + 0.9                                           # nothing touches the board rearward of the pin-3 pads
EDGES = ((PCB_X0, PIN_X_OUT, -1), (PCB_X1, PIN_X_IN, +1))        # edge, its pin row, and the direction away from the board
for x_edge, x_pin, out in EDGES:
    xa, xb = x_edge + out*1.0, x_edge - out*SO_W                   # 1 mm outboard for stiffness
    for i in PEG_PINS:
        yc = PIN_Y[i]
        hang(box(min(xa,xb), max(xa,xb), yc-SO_W/2, yc+SO_W/2, PCB_ZT, SROOF_B+0.01))
        hang(cyl(PEG_D/2, x_pin, yc, PCB_ZT-PEG_H, PCB_ZT+0.5))
hang(box(PCB_XC-2.5, PCB_XC+2.5, PCB_Y1-6.0, PCB_Y1-1.0, USB_ZT+CLR, SROOF_B+0.01))   # rests on the port shell
# third support: a foot on the ESP32-S3 chip. The 7 x 7 QFN sits at 45 deg between the rows, corners pointing at the
# GPIO11/GPIO10 gap, centre almost on the tail roof's front edge; its top is 3.2 under the roof's outer face (caliper,
# 2026-09-13). With the port pad and the four standoffs it gives the board a plane to sit on, mid-span where the pegs
# cannot help. Set 0.5 rearward so it stays under the roof tongue.
CHIP_S, CHIP_H = 7.0, 1.0
CHIP_Y = (PIN_Y[5]+PIN_Y[6])/2
CHIP_TOP = SROOF_T - 3.2
CHIP_FOOT_D, CHIP_FOOT_DY = 3.0, 0.5
hang(cyl(CHIP_FOOT_D/2, PCB_XC, CHIP_Y+CHIP_FOOT_DY, CHIP_TOP, SROOF_B+0.01))
tail = tail.removeSplitter()

# ---------------- CAP SLEEVE (black plate on the cap) ----------------
p = n + CLR
plate = rb_full(p, PLATE_B, PLATE_T)
for x,y in SCREW_XY: plate = plate.cut(cyl(BOSS_R+CLR, x, y, PLATE_B-1, PLATE_T+1))   # bosses pass through
plate = plate.fuse(box(PCB_X0+3.0, PCB_X1-3.0, PCB_Y0, PCB_Y0+1.5, PLATE_T-0.01, PCB_ZB-CLR))   # antenna end rests here (underside assumed bare)
BAR_TOP = PCB_ZB - 0.5                                                              # room for the port's through-hole tabs
plate = plate.fuse(box(PCB_X0, PCB_X1, T-p-0.2, T-o, PLATE_B, BAR_TOP))            # fills the tail liner's board slot below the board
plate = plate.removeSplitter()

# ---------------- CAP (white) ----------------
cap = rb_full(0, CAP_BOT, Z_BOT)
BOSS_TOP = SROOF_B - CLR
for x,y in SCREW_XY:
    cap = cap.fuse(cyl(BOSS_R, x, y, Z_BOT-0.01, BOSS_TOP))
for x,y in SCREW_XY:
    cap = cap.cut(cyl(3.9/2, x, y, CAP_BOT-1, 0)).cut(cyl(7.6/2, x, y, CAP_BOT-1, BOSS_TOP-CAP))   # head recessed to a CAP-thick web under the roof
feat = port_block(T-WALL, T, Z_BOT-0.01)                                          # lower half of the port opening lives on the cap
cap_rim = ring_full(WALL-LIP_T, WALL).common(box(-W, W, -N_BOT-1, T+1, Z_BOT-0.01, Z_BOT+LIP_H-CLR))
feat = feat.fuse(cap_rim).cut(stadium_y(PCB_XC, USB_ZC, USB_W, USB_H, T-WALL-1, T+1))   # rim must not close the port
cap = cap.fuse(feat).removeSplitter()

# ---------------- reference bodies ----------------
MDF_W, MDF_D = 750.0, 580.0
mdf = box(-MDF_W/2, MDF_W/2, 0, MDF_D, -MDF_T, 0)
pcb = box(PCB_X0, PCB_X1, PCB_Y0, PCB_Y1, PCB_ZB, PCB_ZT)
for x in (PIN_X_OUT, PIN_X_IN):
    for y in PIN_Y: pcb = pcb.cut(cyl(PIN_HOLE/2, x, y, PCB_ZB-1, PCB_ZT+1))
usb = stadium_y(PCB_XC, USB_ZC, 8.94, USB_HT, PCB_Y1+1.5-7.35, PCB_Y1+1.5)     # receptacle shell is a stadium too
chip = box(PCB_XC-CHIP_S/2, PCB_XC+CHIP_S/2, CHIP_Y-CHIP_S/2, CHIP_Y+CHIP_S/2, PCB_ZT, CHIP_TOP)
chip.rotate(V(PCB_XC, CHIP_Y, 0), V(0,0,1), 45)
plug= box(PCB_XC-6, PCB_XC+6, PCB_Y1+1.5, PCB_Y1+1.5+20, USB_ZC-3.25, USB_ZC+3.25)
led = box(LED_X-LED_S/2, LED_X+LED_S/2, LED_Y-LED_S/2, LED_Y+LED_S/2, PCB_ZT, PCB_ZT+LED_H)
pad = sbox(PAD_X0, PAD_X1, PAD_V0, PAD_V1, WALL+GAP+SW_PAD, WALL+GAP+SW_PAD+1.2)   # taped into the sleeve recess
# the LED's useful light: loft from the LED's top face to the bar's inner face
led_sq = Part.makePolygon([V(LED_X-LED_S/2,LED_Y-LED_S/2,PCB_ZT+LED_H), V(LED_X+LED_S/2,LED_Y-LED_S/2,PCB_ZT+LED_H),
                           V(LED_X+LED_S/2,LED_Y+LED_S/2,PCB_ZT+LED_H), V(LED_X-LED_S/2,LED_Y+LED_S/2,PCB_ZT+LED_H), V(LED_X-LED_S/2,LED_Y-LED_S/2,PCB_ZT+LED_H)])
bar_rc = Part.makePolygon([spt(-BAR_HW,BAR_V1,BAR_WALL), spt(BAR_HW,BAR_V1,BAR_WALL), spt(BAR_HW,BAR_V0,BAR_WALL), spt(-BAR_HW,BAR_V0,BAR_WALL), spt(-BAR_HW,BAR_V1,BAR_WALL)])
cone = Part.makeLoft([led_sq, bar_rc], True, True)

def add(name, shape, color, transp=0):
    ob = doc.addObject("Part::Feature", name); ob.Shape = shape
    if App.GuiUp: ob.ViewObject.ShapeColor = color; ob.ViewObject.Transparency = transp
    return ob
add("Top",       top,    (0.93,0.92,0.88))
add("Mid",       mid,    (0.88,0.87,0.83))
add("Sleeve",    sleeve, (0.12,0.12,0.12))
add("TailSleeve", tail,  (0.15,0.15,0.15))
add("CapSleeve", plate,  (0.18,0.18,0.18))
add("Cap",       cap,    (0.93,0.92,0.88))
add("ESP32_ref", pcb.fuse(usb).fuse(chip), (0.1,0.35,0.1))
add("LED_ref",   led,   (0.2,0.9,0.3))
add("USBplug_ref", plug, (0.3,0.3,0.3), 60)
add("TTP223_ref", pad, (0.8,0.1,0.1))
add("LightCone_ref", cone, (1.0,0.85,0.2), 70)
add("MDF_ref",  mdf,  (0.55,0.45,0.30), 75)
doc.recompute()
PARTS = ("Top","Mid","Sleeve","TailSleeve","CapSleeve","Cap")
for nm in PARTS:
    s = doc.getObject(nm).Shape; bb=s.BoundBox
    print(nm, "valid:", s.isValid(), "solids:", len(s.Solids), "vol:", round(s.Volume,1),
          "bbox:", [round(v,1) for v in (bb.XMin,bb.XMax,bb.YMin,bb.YMax,bb.ZMin,bb.ZMax)])
print("slope from vertical:", round(ang,1), "deg, length", round(SLOPE_LEN,1), " under-board:", round(-MDF_T-CAP_BOT,2), " T:", round(T,2))
REFS = ("ESP32_ref","LED_ref","USBplug_ref","TTP223_ref","MDF_ref")
pairs = [(a,b) for ia,a in enumerate(PARTS) for b in PARTS[ia+1:]] + [(a,r) for a in PARTS for r in REFS]
for a,b in pairs:
    c = doc.getObject(a).Shape.common(doc.getObject(b).Shape)
    if c.Volume > 1e-6: print("OVERLAP", a, b, round(c.Volume,3))
def dist(a,b): return round(doc.getObject(a).Shape.distToShape(doc.getObject(b).Shape)[0],3)
print("gap top-sleeve:", dist("Top","Sleeve"), " mid-sleeve:", dist("Mid","Sleeve"), " mid-tail:", dist("Mid","TailSleeve"), " sleeve-tail:", dist("Sleeve","TailSleeve"),
      " tail-capsleeve:", dist("TailSleeve","CapSleeve"), " capsleeve-cap:", dist("CapSleeve","Cap"), " tail-cap:", dist("TailSleeve","Cap"), " top-mid:", dist("Top","Mid"))
print("ESP32: tail", dist("TailSleeve","ESP32_ref"), " capsleeve", dist("CapSleeve","ESP32_ref"), " cap", dist("Cap","ESP32_ref"), " mid", dist("Mid","ESP32_ref"),
      " | LED: tail", dist("TailSleeve","LED_ref"), " sleeve", dist("Sleeve","LED_ref"), " LED rear edge to tail roof edge", round(TAIL_Y0-(LED_Y+LED_S/2),2))
print("plastic between finger and pad:", round(PAD_WALL+GAP+SW_PAD,2), " dish depth", DISK_DEPTH, " sphere R", round(R_DISH,1), " rim angle", round(math.degrees(math.asin(DISK_D/2/R_DISH)),1), "deg  Top edges R", EDGE_R, " min wall at a 90-deg corner", round(EDGE_R-(EDGE_R-WALL)*math.sqrt(2),2))
print("pad PCB v:", round(PAD_V0,2), "..", round(PAD_V1,2), " circle at v", round(PAD_CIRCLE_V,2), " gap pad->bar", round(BAR_V0-PAD_V1,2), " bar->corner", round(SLOPE_LEN-BAR_V1,2), " bar v:", round(BAR_V0,2), "..", round(BAR_V1,2), " slope len", round(SLOPE_LEN,1))
under_head = CAP + CLR + SW_ROOF + GAP + ROOF
print("screw: head recess depth", round(BOSS_TOP-CAP-CAP_BOT,2), " plastic under head", round(under_head,2), " -> 4x16 bites", round(16-under_head,1), "mm of MDF, ", SCREW_XY[0][1], "mm from the MDF edge")
cc = (W/2-R_REAR, T-R_REAR)                                    # tail corner arc centre (+X side)
print("boss to PCB:", round(PCB_X0-(SCREW_XY[0][0]+BOSS_R),2), " to standoff", round((PCB_X0-1.0)-(SCREW_XY[0][0]+BOSS_R),2),
      " to tail corner", round((R_REAR-n)-(math.hypot(SCREW_XY[1][0]-cc[0], SCREW_XY[1][1]-cc[1])+BOSS_R),2), " to tail rear wall", round((T-n)-(SCREW_XY[1][1]+BOSS_R),2))
print("board X:", PCB_X0, "..", PCB_X1, " LED X", LED_X, " ribbon slot X", round(RIB_X0,2), "..", round(RIB_X1,2), " Y", round(T-WALL-RIB_DEPTH,2), "..", round(T-WALL,2), " to +X boss", round((SCREW_XY[1][0]-BOSS_R)-RIB_X1,2))
print("standoff height", round(SROOF_B-PCB_ZT,2), " port top to tail roof", round(SROOF_B-USB_ZT,2))
print("chip foot: height", round(SROOF_B-CHIP_TOP,2), " chip top above PCB", round(CHIP_TOP-PCB_ZT,2), " at Y", round(CHIP_Y+CHIP_FOOT_DY,2), " chip centre Y", round(CHIP_Y,2),
      " foot front edge to roof tongue front", round((CHIP_Y+CHIP_FOOT_DY-CHIP_FOOT_D/2)-(-BACK-GAP-SW-CLR),2), " foot-chip", dist("TailSleeve","ESP32_ref"))
print("pegs at pins", [i+1 for i in PEG_PINS], "both rows, peg-to-hole gap", round((PIN_HOLE-PEG_D)/2,2), " peg tip below board", round(PEG_H-1.2,2), " retention Y max", round(PIN_Y[min(PEG_PINS)]+SO_W/2,2), "< first wired pad at", round(WIRED_Y,2),
      " front standoff edge", round(PIN_Y[max(PEG_PINS)]-SO_W/2,2), "vs tail roof front", round(TAIL_Y0,2))
print("USB notch X:", round(PCB_XC-USB_W/2-USB_HORN,1), "..", round(PCB_XC+USB_W/2+USB_HORN,1), " ribbon slot X:", RIB_X0, "..", RIB_X1, " flat rear wall to X ±", W/2-R_REAR)

def show_section(keep_x_positive=True):
    half = box(0 if keep_x_positive else -100, 100 if keep_x_positive else 0, -100, 100, -100, 100)
    for nm in PARTS+("ESP32_ref","LED_ref","USBplug_ref","TTP223_ref","LightCone_ref"):
        ob = doc.getObject(nm)
        sc = doc.getObject(nm+"_sec") or doc.addObject("Part::Feature", nm+"_sec")
        sc.Shape = ob.Shape.common(half); sc.ViewObject.ShapeColor = ob.ViewObject.ShapeColor; sc.ViewObject.Transparency = 0
        ob.ViewObject.Visibility = False
    doc.getObject("MDF_ref").ViewObject.Visibility = False
    doc.recompute()
def show_full():
    for ob in doc.Objects: ob.ViewObject.Visibility = not ob.Name.endswith("_sec")
    doc.recompute()
if App.GuiUp: Gui.SendMsgToActiveView("ViewFit")

# ---- outputs next to this script: <part>.stl (print) + .step, and the FreeCAD document (skipped when the caller
# seeds the namespace with EXPORT = False, e.g. assembly.py previewing)
import os as _os
if globals().get('EXPORT', True):
    _CAD = _os.path.dirname(_os.path.abspath(__file__)) if '__file__' in globals() and 'tools/cad' in __file__ else '/home/cristian/Source/esphome-litterbox-monitor-enclosure/tools/cad'
    for _nm in PARTS:
        export_stl(doc.getObject(_nm).Shape, _os.path.join(_CAD, 'brain_shell_%s.stl' % _nm.lower()))
        doc.getObject(_nm).Shape.exportStep(_os.path.join(_CAD, 'brain_shell_%s.step' % _nm.lower()))
    doc.saveAs(_os.path.join(_CAD, 'brain_shell.FCStd'))
