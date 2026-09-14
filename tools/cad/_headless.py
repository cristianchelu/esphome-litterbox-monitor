# run a tools/cad script under FreeCADCmd (no GUI): flatpak run --command=FreeCADCmd org.freecad.FreeCAD tools/cad/_headless.py [script]
# Stubs FreeCADGui; the scripts guard their own ViewObject/view calls with App.GuiUp. Default script: assembly.py (runs the rest).
import sys, types, os
gui = types.ModuleType("FreeCADGui"); gui.SendMsgToActiveView = lambda *a, **k: None
sys.modules["FreeCADGui"] = gui
name = sys.argv[-1] if sys.argv[-1].endswith(".py") and not sys.argv[-1].endswith("_headless.py") else "assembly.py"
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
exec(compile(open(path).read(), path, "exec"), {"__file__": path, "__name__": "__main__"})
