"""Shared helpers for the *_param.py generators: a Params spreadsheet, fully constrained sketches whose dimensions
are expressions on that sheet, and PartDesign features inserted in timeline order. Everything here is plain
FreeCAD scripting; the generators only read nicer for it."""
import FreeCAD as App, Part, Sketcher, math
from FreeCAD import Vector as V

doc = None
vals = {}
GUI = App.GuiUp
# the sheet's formula functions, for evaluating the same formula text on the Python side
_FUNCS = {"round": round, "ceil": math.ceil, "floor": math.floor, "sqrt": math.sqrt, "hypot": math.hypot, "abs": abs,
          "min": min, "max": max, "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
          "sin": lambda a: math.sin(math.radians(a)), "cos": lambda a: math.cos(math.radians(a)), "tan": lambda a: math.tan(math.radians(a))}
# angles are degrees on both sides: the sheet's atan2 yields a "deg" quantity that its sin/cos accept

def init(name, params):
    """fresh document `name` with a Params spreadsheet built from (alias, value-or-'=formula', note) rows; a row with
    value None is a bold section header. Returns (doc, sheet); numeric values land in pdlib.vals for seeding sketches."""
    global doc, vals
    if name in App.listDocuments(): App.closeDocument(name)
    doc = App.newDocument(name)
    vals = {}
    ss = doc.addObject("Spreadsheet::Sheet", "Params")
    ss.set("A1", "Parameter"); ss.set("B1", "Value"); ss.set("C1", "Note")
    row = 2
    for alias, val, note in params:
        if val is None:
            row += 1; ss.set("A%d" % row, alias); ss.setStyle("A%d" % row, "bold"); row += 1; continue
        ss.set("A%d" % row, alias); ss.set("C%d" % row, note)
        if isinstance(val, str):
            ss.set("B%d" % row, val); vals[alias] = float(eval(val[1:].replace(";", ",").replace("^", "**"), dict(_FUNCS), dict(vals)))
        else:
            ss.set("B%d" % row, str(val)); vals[alias] = float(val)
        ss.setAlias("B%d" % row, alias)
        row += 1
    ss.setColumnWidth("A", 90); ss.setColumnWidth("C", 330)
    doc.recompute()
    return doc, ss

def ev(expr):
    """numeric value of a Params.* expression, for seeding sketch geometry"""
    return float(eval(expr.replace("Params.", ""), {}, dict(vals)))
def E(obj, prop, expr): obj.setExpression(prop, expr)
def hide(*objs):
    if GUI:
        for o in objs: o.ViewObject.Visibility = False
def paint(obj, rgb):
    if GUI:
        try: obj.ViewObject.ShapeColor = rgb
        except Exception: pass

# ---------------- sketches ----------------
def plane(body, role):
    return [f for f in body.Origin.OriginFeatures if f.Role == role][0]

def sketch(body, name, support, offset="0", world=True):
    """sketch on one of the body's origin planes (by role) or on a datum plane. `offset` is an expression: with
    world=True the world coordinate along the plane's axis (so an XZ sketch at offset "5" sits at Y = 5 whichever way
    that plane's normal points); with world=False a distance along the plane's own normal."""
    sk = body.newObject("Sketcher::SketchObject", name)
    sup = plane(body, support) if isinstance(support, str) else support
    sk.AttachmentSupport = [(sup, "")]; sk.MapMode = "FlatFace"
    doc.recompute()
    if world:
        n = sk.getGlobalPlacement().Rotation.multVec(V(0, 0, 1)); ax = max(range(3), key=lambda k: abs(n[k]))
        if n[ax] < 0: offset = "-(%s)" % offset
    E(sk, "AttachmentOffset.Base.z", offset)
    doc.recompute()
    return sk

def datum_plane(body, name, support=None, offset="0"):
    """datum plane: on an origin plane (by role) shifted `offset` along its axis (world coordinate), or free (no support)
    for the caller to place through expressions on Placement"""
    dp = body.newObject("PartDesign::Plane", name)
    if support is None:
        dp.MapMode = "Deactivated"
    else:
        dp.AttachmentSupport = [(plane(body, support), "")]; dp.MapMode = "FlatFace"; doc.recompute()
        n = dp.getGlobalPlacement().Rotation.multVec(V(0, 0, 1)); ax = max(range(3), key=lambda k: abs(n[k]))
        E(dp, "AttachmentOffset.Base.z", ("-(%s)" % offset) if n[ax] < 0 else offset)
    if GUI: dp.ViewObject.Visibility = False
    doc.recompute()
    return dp

def normal_sign(sk):
    """sign of the dominant world component of the sketch normal (pads go along +normal, pockets along -normal)"""
    n = sk.getGlobalPlacement().Rotation.multVec(V(0, 0, 1)); ax = max(range(3), key=lambda k: abs(n[k]))
    return 1 if n[ax] > 0 else -1

class Frame:
    """world <-> sketch coordinates for a sketch on an origin plane. `axes` names the world axes (0=X,1=Y,2=Z) that
    the sketch's local x and y should land on; u()/w() turn world expressions into local ones, P() seeds points."""
    def __init__(self, sk, axes):
        rot = sk.getGlobalPlacement().Rotation
        self.s = []
        for i, loc in enumerate((V(1, 0, 0), V(0, 1, 0))):
            wv = rot.multVec(loc); ax = max(range(3), key=lambda k: abs(wv[k]))
            assert ax == axes[i], "%s: sketch local %s lands on world axis %d, wanted %d" % (sk.Name, "xy"[i], ax, axes[i])
            self.s.append(1 if wv[ax] > 0 else -1)
        n = rot.multVec(V(0, 0, 1)); self.normal_sign = 1 if n[max(range(3), key=lambda k: abs(n[k]))] > 0 else -1
        self.reflected = self.s[0] * self.s[1] < 0
    def u(self, expr): return "%s(%s)" % ("-" if self.s[0] < 0 else "", expr)
    def w(self, expr): return "%s(%s)" % ("-" if self.s[1] < 0 else "", expr)
    def P(self, a, b): return V(self.s[0] * a, self.s[1] * b, 0)

def dist_constraint(sk, kind, g1, p1, g2, p2, expr, name):
    """DistanceX/Y between two sketch points, driven by expr. Sketcher wants a positive datum, so the point order
    follows the sign of the seed value."""
    v = ev(expr)
    if v < 0: g1, p1, g2, p2, expr, v = g2, p2, g1, p1, "-(%s)" % expr, -v
    i = sk.addConstraint(Sketcher.Constraint(kind, g1, p1, g2, p2, v))
    sk.renameConstraint(i, name); E(sk, ".Constraints." + name, expr)

def rrect(sk, x0, x1, y0, y1, r, tag=""):
    """rounded rectangle in sketch coordinates, fully constrained: x0/y0 corner, width, height, radius (expressions)"""
    X0, X1, Y0, Y1, R = (ev(e) for e in (x0, x1, y0, y1, r))
    L = lambda a, b: sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
    A = lambda c, a1, a2: sk.addGeometry(Part.ArcOfCircle(Part.Circle(V(c[0], c[1], 0), V(0, 0, 1), R), math.radians(a1), math.radians(a2)), False)
    bot = L((X0+R, Y0), (X1-R, Y0)); br = A((X1-R, Y0+R), -90, 0)
    rgt = L((X1, Y0+R), (X1, Y1-R)); tr = A((X1-R, Y1-R), 0, 90)
    top = L((X1-R, Y1), (X0+R, Y1)); tl = A((X0+R, Y1-R), 90, 180)
    lft = L((X0, Y1-R), (X0, Y0+R)); bl = A((X0+R, Y0+R), 180, 270)
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    for a, b in ((bot, br), (br, rgt), (rgt, tr), (tr, top), (top, tl), (tl, lft), (lft, bl), (bl, bot)):
        C("Tangent", a, 2, b, 1)                      # end of a meets start of b, tangent
    C("Horizontal", bot); C("Horizontal", top); C("Vertical", rgt); C("Vertical", lft)
    C("Equal", br, tr); C("Equal", tr, tl); C("Equal", tl, bl)
    i = C("Radius", br, R); sk.renameConstraint(i, "radius" + tag); E(sk, ".Constraints.radius" + tag, r)
    dist_constraint(sk, "DistanceX", -1, 1, lft, 1, x0, "x0" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, bot, 1, y0, "y0" + tag)
    dist_constraint(sk, "DistanceX", lft, 1, rgt, 1, "(%s) - (%s)" % (x1, x0), "width" + tag)
    dist_constraint(sk, "DistanceY", bot, 1, top, 1, "(%s) - (%s)" % (y1, y0), "height" + tag)

def rrect_c(sk, x0, x1, y0, y1, r_bot, r_top, tag=""):
    """rectangle with the y0 corners rounded r_bot and the y1 corners r_top (either None for square corners)"""
    if r_bot is not None and r_top is not None and r_bot == r_top: return rrect(sk, x0, x1, y0, y1, r_bot, tag)
    if r_bot is None and r_top is None: return rect(sk, x0, x1, y0, y1, tag)
    X0, X1, Y0, Y1 = (ev(e) for e in (x0, x1, y0, y1))
    RB = ev(r_bot) if r_bot is not None else 0.0; RT = ev(r_top) if r_top is not None else 0.0
    L = lambda a, b: sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
    A = lambda c, r, a1, a2: sk.addGeometry(Part.ArcOfCircle(Part.Circle(V(c[0], c[1], 0), V(0, 0, 1), r), math.radians(a1), math.radians(a2)), False)
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    bot = L((X0+RB, Y0), (X1-RB, Y0)); rgt = L((X1, Y0+RB), (X1, Y1-RT)); top = L((X1-RT, Y1), (X0+RT, Y1)); lft = L((X0, Y1-RT), (X0, Y0+RB))
    C("Horizontal", bot); C("Horizontal", top); C("Vertical", rgt); C("Vertical", lft)
    if r_bot is not None:
        br = A((X1-RB, Y0+RB), RB, -90, 0); bl = A((X0+RB, Y0+RB), RB, 180, 270)
        C("Tangent", bot, 2, br, 1); C("Tangent", br, 2, rgt, 1); C("Tangent", lft, 2, bl, 1); C("Tangent", bl, 2, bot, 1); C("Equal", br, bl)
        i = C("Radius", br, RB); sk.renameConstraint(i, "r_bot" + tag); E(sk, ".Constraints.r_bot" + tag, r_bot)
    else:
        C("Coincident", bot, 2, rgt, 1); C("Coincident", lft, 2, bot, 1)
    if r_top is not None:
        tr = A((X1-RT, Y1-RT), RT, 0, 90); tl = A((X0+RT, Y1-RT), RT, 90, 180)
        C("Tangent", rgt, 2, tr, 1); C("Tangent", tr, 2, top, 1); C("Tangent", top, 2, tl, 1); C("Tangent", tl, 2, lft, 1); C("Equal", tr, tl)
        i = C("Radius", tr, RT); sk.renameConstraint(i, "r_top" + tag); E(sk, ".Constraints.r_top" + tag, r_top)
    else:
        C("Coincident", rgt, 2, top, 1); C("Coincident", top, 2, lft, 1)
    dist_constraint(sk, "DistanceX", -1, 1, lft, 1, x0, "x0" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, bot, 1, y0, "y0" + tag)
    dist_constraint(sk, "DistanceX", lft, 1, rgt, 1, "(%s) - (%s)" % (x1, x0), "width" + tag)
    dist_constraint(sk, "DistanceY", bot, 1, top, 1, "(%s) - (%s)" % (y1, y0), "height" + tag)

def stadium(sk, x0, x1, y0, y1, tag="", P=None):
    """slot along x between x0 and x1, semicircular ends of radius (y1-y0)/2. P maps (x, y) to sketch coords."""
    P = P or (lambda a, b: V(a, b, 0))
    X0, X1, Y0, Y1 = (ev(e) for e in (x0, x1, y0, y1)); R = (Y1 - Y0) / 2; YC = (Y0 + Y1) / 2
    L = lambda a, b: sk.addGeometry(Part.LineSegment(P(*a), P(*b)), False)
    A = lambda c, a1, a2: sk.addGeometry(Part.ArcOfCircle(Part.Circle(P(*c), V(0, 0, 1), R), math.radians(a1), math.radians(a2)), False)
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    flip = P(1, 1).x * P(1, 1).y < 0            # a reflected mapping runs the arcs the other way round
    bot = L((X0+R, Y0), (X1-R, Y0)); top = L((X1-R, Y1), (X0+R, Y1))
    ar = A((X1-R, YC), -90, 90) if not flip else A((X1-R, YC), 90, 270)
    al = A((X0+R, YC), 90, 270) if not flip else A((X0+R, YC), -90, 90)
    s, e = (1, 2) if not flip else (2, 1)
    C("Tangent", bot, 2, ar, s); C("Tangent", ar, e, top, 1); C("Tangent", top, 2, al, s); C("Tangent", al, e, bot, 1)
    C("Horizontal", bot); C("Horizontal", top)                   # (equal radii follow from the two parallel tangents)
    i = C("Radius", ar, R); sk.renameConstraint(i, "r" + tag); E(sk, ".Constraints.r" + tag, "((%s) - (%s)) / 2" % (y1, y0))
    ux = lambda e: e if P(1, 0).x > 0 else "-(%s)" % e            # world-to-sketch sign for a reflected mapping
    uy = lambda e: e if P(0, 1).y > 0 else "-(%s)" % e
    dist_constraint(sk, "DistanceX", -1, 1, al, 3, ux("(%s) + ((%s) - (%s)) / 2" % (x0, y1, y0)), "x_left" + tag)
    dist_constraint(sk, "DistanceX", -1, 1, ar, 3, ux("(%s) - ((%s) - (%s)) / 2" % (x1, y1, y0)), "x_right" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, al, 3, uy("((%s) + (%s)) / 2" % (y0, y1)), "y_centre" + tag)
    return bot, top, ar, al

def circles2(sk, d, px, y, tag=""):
    """two equal circles at (-px, y) and (px, y), mirror images about the V axis"""
    sx, Y, D = ev(px), ev(y), ev(d)
    c0 = sk.addGeometry(Part.Circle(V(-sx, Y, 0), V(0, 0, 1), D / 2), False); c1 = sk.addGeometry(Part.Circle(V(sx, Y, 0), V(0, 0, 1), D / 2), False)
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    C("Symmetric", c0, 3, c1, 3, -2); C("Equal", c0, c1)
    i = C("Diameter", c0, D); sk.renameConstraint(i, "d" + tag); E(sk, ".Constraints.d" + tag, d)
    dist_constraint(sk, "DistanceX", -1, 1, c0, 3, "-(%s)" % px, "x" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, c0, 3, y, "y" + tag)
    return c0, c1

def rect(sk, x0, x1, y0, y1, tag=""):
    X0, X1, Y0, Y1 = (ev(e) for e in (x0, x1, y0, y1))
    L = lambda a, b: sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
    bot = L((X0, Y0), (X1, Y0)); rgt = L((X1, Y0), (X1, Y1)); top = L((X1, Y1), (X0, Y1)); lft = L((X0, Y1), (X0, Y0))
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    for a, b in ((bot, rgt), (rgt, top), (top, lft), (lft, bot)): C("Coincident", a, 2, b, 1)
    C("Horizontal", bot); C("Horizontal", top); C("Vertical", rgt); C("Vertical", lft)
    dist_constraint(sk, "DistanceX", -1, 1, lft, 1, x0, "x0" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, bot, 1, y0, "y0" + tag)
    dist_constraint(sk, "DistanceX", lft, 1, rgt, 1, "(%s) - (%s)" % (x1, x0), "width" + tag)
    dist_constraint(sk, "DistanceY", bot, 1, top, 1, "(%s) - (%s)" % (y1, y0), "height" + tag)

def circle(sk, x, y, d, tag=""):
    X, Y, D = (ev(e) for e in (x, y, d))
    c = sk.addGeometry(Part.Circle(V(X, Y, 0), V(0, 0, 1), D / 2), False)
    i = sk.addConstraint(Sketcher.Constraint("Diameter", c, D)); sk.renameConstraint(i, "d" + tag); E(sk, ".Constraints.d" + tag, d)
    dist_constraint(sk, "DistanceX", -1, 1, c, 3, x, "x" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, c, 3, y, "y" + tag)
    return c

def circles4(sk, d, px, py, tag=""):
    """a 2x2 pattern: four equal circles at (+-px, +-py), mirror images of the first about both axes"""
    sx, sy, D = ev(px), ev(py), ev(d)
    c = [sk.addGeometry(Part.Circle(V(x * sx, y * sy, 0), V(0, 0, 1), D / 2), False) for x, y in ((-1, -1), (1, -1), (-1, 1), (1, 1))]
    C = lambda *a: sk.addConstraint(Sketcher.Constraint(*a))
    C("Symmetric", c[0], 3, c[1], 3, -2)             # about the V axis
    C("Symmetric", c[0], 3, c[2], 3, -1)             # about the H axis
    C("Symmetric", c[0], 3, c[3], 3, -1, 1)          # about the origin
    for k in (1, 2, 3): C("Equal", c[0], c[k])
    i = C("Diameter", c[0], D); sk.renameConstraint(i, "d" + tag); E(sk, ".Constraints.d" + tag, d)
    dist_constraint(sk, "DistanceX", -1, 1, c[0], 3, "-(%s)" % px, "pitch_x" + tag)
    dist_constraint(sk, "DistanceY", -1, 1, c[0], 3, "-(%s)" % py, "pitch_y" + tag)
    return c

# ---------------- features ----------------
def pad(body, sk, name, length, reversed_=False, midplane=False):
    f = body.newObject("PartDesign::Pad", name); f.Profile = sk; f.Reversed = reversed_; f.Midplane = midplane
    E(f, "Length", length); hide(sk); doc.recompute(); return f
def pocket(body, sk, name, length=None, midplane=False, reversed_=False):
    f = body.newObject("PartDesign::Pocket", name); f.Profile = sk
    if length is None: f.Type = "ThroughAll"
    else: f.Type = "Length"; E(f, "Length", length)
    f.Midplane = midplane; f.Reversed = reversed_; hide(sk); doc.recompute(); return f
def fillet(body, base, name, radius, pred):
    """PartDesign fillet on the edges of `base` picked by pred(edge) (or listed by index); picked once, tracked by the
    element map after"""
    edges = ["Edge%d" % (i + 1) for i in pred] if isinstance(pred, (list, tuple)) else \
            ["Edge%d" % (i + 1) for i, e in enumerate(base.Shape.Edges) if pred(e)]
    assert edges, name + ": no edges matched"
    f = body.newObject("PartDesign::Fillet", name); f.Base = (base, edges); E(f, "Radius", radius)
    doc.recompute(); return f
def _place_after(body, f, feature):
    # newObject appends a Transformed feature at the end of the body without moving the Tip; place it by hand
    body.insertObject(f, feature, True); body.Tip = f
def mirrored(body, feature, name, role):
    f = doc.addObject("PartDesign::Mirrored", name); f.Originals = [feature]; f.MirrorPlane = (plane(body, role), [""])
    _place_after(body, f, feature); doc.recompute(); return f
def mirrored2(body, feature, name, roles=("YZ_Plane", "XZ_Plane")):
    """the feature and its images in both planes: a MultiTransform of two mirrors"""
    mt = doc.addObject("PartDesign::MultiTransform", name); mt.Originals = [feature]
    ts = []
    for role in roles:
        m = doc.addObject("PartDesign::Mirrored", name + "_" + role.split("_")[0]); m.MirrorPlane = (plane(body, role), [""]); ts.append(m)
    mt.Transformations = ts
    _place_after(body, mt, feature); doc.recompute(); return mt
def thickness(body, base, name, value, pred):
    """hollow the body inward by `value`, opening the faces of `base` picked by pred(face) (Arc join + intersection:
    this is what reproduces a boolean of inward offsets, and the only mode that gave a valid solid)"""
    faces = ["Face%d" % (i + 1) for i, f in enumerate(base.Shape.Faces) if pred(f)]
    assert faces, name + ": no faces matched"
    f = body.newObject("PartDesign::Thickness", name); f.Base = (base, faces); E(f, "Value", value)
    f.Reversed = True; f.Mode = "Skin"; f.Join = "Arc"; f.Intersection = True
    doc.recompute(); return f
def derive(body, source, name):
    """start `body` from another body's shape through a SubShapeBinder (kept in sync, unlike a Boolean tool, which a
    body can only be for one Boolean at a time)"""
    binder = doc.addObject("PartDesign::SubShapeBinder", name); binder.Support = [(source, "")]
    body.BaseFeature = binder; hide(binder); doc.recompute(); return binder
def boolean(body, name, kind, tools):
    f = body.newObject("PartDesign::Boolean", name); f.Type = kind; f.addObjects(list(tools))
    doc.recompute(); return f
def sub_sphere(body, name, radius, support, ox, oy, oz):
    """subtractive sphere attached to a datum plane, centre at (ox, oy, oz) in the plane's frame (expressions)"""
    f = body.newObject("PartDesign::SubtractiveSphere", name); E(f, "Radius", radius)
    f.AttachmentSupport = [(support, "")]; f.MapMode = "ObjectXY"
    E(f, "AttachmentOffset.Base.x", ox); E(f, "AttachmentOffset.Base.y", oy); E(f, "AttachmentOffset.Base.z", oz)
    doc.recompute(); return f
def mirrored_about(body, features, name, plane_obj):
    """Mirrored of one or more features about a datum plane, placed after the last of them"""
    f = doc.addObject("PartDesign::Mirrored", name); f.Originals = list(features); f.MirrorPlane = (plane_obj, [""])
    _place_after(body, f, features[-1]); doc.recompute(); return f
def pipe(body, profile, spine, name):
    f = body.newObject("PartDesign::AdditivePipe", name)
    f.Profile = profile; f.Spine = (spine, []); f.Mode = "Standard"; f.Transition = "Transformed"
    hide(profile, spine); doc.recompute(); return f
def finish(body, rgb):
    for o in body.Group: hide(o)
    if GUI: body.Tip.ViewObject.Visibility = True
    paint(body.Tip, rgb); body.Tip.Refine = True; doc.recompute()

# ---------------- checks ----------------
def check(bodies):
    for o in doc.Objects:
        if o.TypeId == "Sketcher::SketchObject" and not o.FullyConstrained: print("NOT fully constrained:", o.Name)
    bad = [o.Name for o in doc.Objects if "Invalid" in o.State]
    if bad: print("INVALID:", bad)
    for b in bodies:
        s = b.Shape
        print(b.Name, "valid:", s.isValid(), "solids:", len(s.Solids), "vol:", round(s.Volume, 1),
              "features:", len([o for o in b.Group if o.isDerivedFrom("PartDesign::Feature")]))
    if GUI:
        import FreeCADGui as Gui
        Gui.SendMsgToActiveView("ViewFit")

def compare(ref_doc_name, pairs):
    """symmetric difference of each (body name, reference object name) against a document built by the old script"""
    if ref_doc_name not in App.listDocuments(): print("no", ref_doc_name, "open to compare against"); return
    S = App.getDocument(ref_doc_name)
    for bn, rn in pairs:
        a, b = doc.getObject(bn).Shape, S.getObject(rn).Shape
        d1, d2 = a.cut(b), b.cut(a)
        print("%-6s vs %-9s symmetric difference %.3f mm3" % (bn, rn, d1.Volume + d2.Volume))
        for tag, d in (("only here", d1), ("only ref", d2)):
            for s in sorted(d.Solids, key=lambda s: -s.Volume)[:4]:
                if s.Volume > 0.01:
                    bb = s.BoundBox; print("    %s %.2f mm3  x %.1f..%.1f  y %.1f..%.1f  z %.2f..%.2f" % (tag, s.Volume, bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax))
