import FreeCAD as App, Part, math
from FreeCAD import Vector as V, Placement, Rotation

# Cable channels taped to the MDF underside: arched profile (short straight walls + semicircular crown) with two tape
# flanges, built along +X with the tape face at Z = 0 and the body hanging to -Z. Sections <= MAX_LEN for the A1 mini.
# Joins: the +X end carries a 6 mm spigot (the arch continued as a thin inward skin) that slides into the plain -X end
# of the next section. Exported STLs are flipped flanges-down for printing: walls and spigot rise from the bed, the
# only bridge is ~2 mm at the crown.
WALL, FLANGE, FLANGE_T = 1.2, 4.0, 1.2
H_WALL = 1.0                          # straight wall under the arch (gives a flat 5-wire ribbon room at the edges)
CLR = 0.1
SPIGOT_L, SPIGOT_T = 6.0, 0.6
MAX_LEN = 170.0
PROFILES = {"ribbon": 8.0}            # inner width; inner height at the crown = H_WALL + width/2

def box(x0,x1,y0,y1,z0,z1): return Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0))
def arch(x0, x1, half_w, z_top, deep=True):
    """solid under z_top: straight down H_WALL then a semicircle of radius half_w (a tunnel shape, open above z_top)"""
    zc = z_top - H_WALL
    body = box(x0, x1, -half_w, half_w, zc, z_top + (5 if deep else 0))
    cyl = Part.makeCylinder(half_w, x1-x0, V(x0, 0, zc), V(1,0,0))
    return body.fuse(cyl.common(box(x0-1, x1+1, -half_w-1, half_w+1, zc-half_w-1, zc)))

def section(kind, length, spigot=True):
    iw = PROFILES[kind]; ow = iw/2 + WALL
    s = arch(0, length, ow, 0, deep=False).cut(arch(-1, length+1, iw/2, 0))
    for sy in (1,-1):
        s = s.fuse(box(0, length, min(sy*ow, sy*(ow+FLANGE)), max(sy*ow, sy*(ow+FLANGE)), -FLANGE_T, 0))
    if spigot:
        m = arch(length, length+SPIGOT_L, iw/2-CLR, 0, deep=False)                 # skin 0.1 inside the next section's bore
        m = m.fuse(arch(length-1.0, length+0.01, iw/2+0.05, 0, deep=False))          # 1 mm root grown into this section's wall
        m = m.cut(arch(length-2, length+SPIGOT_L+1, iw/2-CLR-SPIGOT_T, 0))
        s = s.fuse(m)
    return s.removeSplitter()

def split(total, max_len=MAX_LEN):
    n = max(1, math.ceil(total/max_len)); return [total/n]*n

def run(kind, p0, p1, gap0=2.0, gap1=2.0):
    """straight run from world point p0 to p1 (Z = tape face); returns [(shape, placement, length)]"""
    d = V(p1.x-p0.x, p1.y-p0.y, 0); L = d.Length; u = d.normalize()
    ang = math.degrees(math.atan2(u.y, u.x))
    lens = split(L - gap0 - gap1)
    out=[]; x = gap0
    for i,l in enumerate(lens):
        sh = section(kind, l, spigot=(i < len(lens)-1))
        pl = Placement(V(p0.x + u.x*x, p0.y + u.y*x, p0.z), Rotation(V(0,0,1), ang))
        out.append((sh, pl, l)); x += l
    return out

def export_print(shape, path):
    """flip flanges-down (print orientation) and write STL"""
    import MeshPart
    s = shape.copy(); s.rotate(V(0,0,0), V(1,0,0), 180); s.translate(V(0,0,-s.BoundBox.ZMin))
    MeshPart.meshFromShape(Shape=s, LinearDeflection=0.05, AngularDeflection=0.35, Relative=False).write(path)
