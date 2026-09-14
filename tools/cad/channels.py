import FreeCAD as App, Part, math
from FreeCAD import Vector as V, Placement, Rotation

# Wire channels taped to the MDF underside (two widths: RIBBON for the HX711 -> brain leads, CELL for the load cells'
# three thin leads): a U groove open toward the board, cut into the top of a flat bar whose flanks slope 45 deg so the
# tape lands on top overhang nothing. Built along +X with the tape face at Z = 0 and the body hanging to -Z. Sections
# are plain bars <= MAX_LEN for the A1 mini, cut to length on the bench and butted (the groove is open to the MDF, a
# joint is just a line the wires cross); print them floor-down with sparse infill, the flanks are only there for the
# tape. No end pieces: each end bar runs NOTCH_IN under the enclosure wall through a notch_w x notch_h notch and stops on
# the plate step inside, so the length error of a cut lands at the middle joint. No bridges, the only overhangs are the
# 45-deg flanks.
WALL, FLOOR = 0.8, 0.6                # min wall beside the groove at the floor (two perimeters), floor under the wires (three layers)
CLR = 0.1
MAX_LEN = 170.0
NOTCH_IN = 5.0                        # how far a bar end goes past the enclosure's wall face

class Profile:
    """groove in_w x in_h, tape land 'margin' each side of it on the top face; derived: bar height, half width at the
    tape face (h less at the floor, 45 deg) and the notch the enclosures cut for the bar"""
    def __init__(self, name, in_w, in_h, margin):
        self.name, self.in_w, self.in_h, self.margin = name, in_w, in_h, margin
        self.h = FLOOR + in_h
        self.top_hw = in_w/2 + margin
        assert self.top_hw - self.h - in_w/2 >= WALL - 1e-9, "%s: walls thinner than %s at the floor" % (name, WALL)
        self.notch_w, self.notch_h = 2*self.top_hw + 0.5, self.h + 0.3
RIBBON = Profile("ribbon", 8.0, 2.0, 4.0)    # HX711 -> brain: five breadboard wires side by side measure 7 x 1.4
                                             # bar 16 / 10.8 x 2.6, notch 16.5 x 2.9 (the brain's slot can be 18.2 at most)
CELL   = Profile("cell", 3.0, 1.2, 3.5)      # foot -> HX711: the load cell's three thin leads measure ~1.7 x 0.7
                                             # bar 10 / 6.4 x 1.8, notch 10.5 x 2.1

def box(x0,x1,y0,y1,z0,z1): return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))
def prism_x(pts_yz, x0, x1):
    """extrude a YZ polygon along X"""
    w = Part.makePolygon([V(x0,y,z) for y,z in pts_yz] + [V(x0,*pts_yz[0])])
    return Part.Face(w).extrude(V(x1-x0,0,0))

def section(p, length):
    bar = prism_x([(-p.top_hw+p.h, -p.h), (p.top_hw-p.h, -p.h), (p.top_hw, 0), (-p.top_hw, 0)], 0, length)
    return bar.cut(box(-1, length+1, -p.in_w/2, p.in_w/2, -p.h+FLOOR, 1)).removeSplitter()

def split(total, max_len=MAX_LEN):
    n = max(1, math.ceil(total/max_len)); return [total/n]*n

def run(p, p0, p1):
    """straight run of profile p between two enclosure wall faces p0, p1 (Z = tape face), the end bars reaching NOTCH_IN
    inside each. Returns [(shape, placement, length)]"""
    d = V(p1.x-p0.x, p1.y-p0.y, 0); L = d.Length; u = d.normalize()
    ang = math.degrees(math.atan2(u.y, u.x))
    secs=[]; x = -NOTCH_IN
    for l in split(L + 2*NOTCH_IN):
        pl = Placement(V(p0.x + u.x*x, p0.y + u.y*x, p0.z), Rotation(V(0,0,1), ang))
        secs.append((section(p, l), pl, l)); x += l
    return secs

def export_print(shape, path):
    """write STL in print orientation: floor on the bed, groove up"""
    import MeshPart
    s = shape.copy(); s.translate(V(0,0,-s.BoundBox.ZMin))
    MeshPart.meshFromShape(Shape=s, LinearDeflection=0.05, AngularDeflection=0.35, Relative=False).write(path)
