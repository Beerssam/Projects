#!/usr/bin/env python3
"""Dashboard fullscreen interaction fix + smaller place labels.

Sam (2026-11-23 17:46 CST): in FULLSCREEN the map is completely dead --
nothing on the map responds (no drag, no pinch, no +/- buttons), while
tap still works (label popups open). Regular page untested. The earlier
overlay fix (polylines/ring interactive:false) did not cure it, so the
cause is in the fullscreen entry itself, not the overlays.

Fixes here:
1. touch-action: the browser can steal drag/pinch for page scroll/zoom
   when the map goes position:fixed. Force `touch-action: none` (and
   `overscroll-behavior: none`) on the fullscreen map so gestures reach
   Leaflet. Tap still works because it is a plain click event, which is
   why popups kept working while drag/pinch died.
2. Refit: the single invalidateSize() 60 ms after entering fullscreen can
   fire before the mobile browser settles the dynamic viewport height
   (100dvh / toolbar animation), leaving Leaflet with a stale size and
   dead interaction handlers. Now refit at several points (immediately,
   requestAnimationFrame, 150 ms, 400 ms) and explicitly re-enable the
   interaction handlers (dragging / touchZoom / scrollWheelZoom /
   doubleClickZoom) on both enter and exit. Also refit on
   visualViewport resize (mobile toolbar show/hide) while fullscreen.
3. Place labels smaller again: 9px -> 7px, padding 1px 4px -> 0 3px,
   radius 4px -> 3px (Sam: they still seem kinda large).

Target: /home/asl/ai_dashboard.py (must have the fullscreen fix + trail4b).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_fsfix2_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

REFIT = ("(function(){ function refit(){ adsbMap.invalidateSize(); "
         "try{ adsbMap.dragging.enable(); adsbMap.touchZoom.enable(); "
         "adsbMap.scrollWheelZoom.enable(); adsbMap.doubleClickZoom.enable(); }catch(e){} } "
         "refit(); requestAnimationFrame(refit); setTimeout(refit, 150); setTimeout(refit, 400); })();")

EDITS = [
    ("Fullscreen map: force touch-action none so drag/pinch reach Leaflet",
     "padding: 0 !important; border: none !important; }",
     "padding: 0 !important; border: none !important; touch-action: none !important; overscroll-behavior: none !important; }"),
    ("Enter fullscreen: robust refit + re-enable interaction handlers",
     "document.getElementById('map-fs-exit').classList.add('map-fs-show'); setTimeout(function(){ adsbMap.invalidateSize(); }, 60); };",
     "document.getElementById('map-fs-exit').classList.add('map-fs-show'); " + REFIT + " };"),
    ("Exit fullscreen: robust refit + re-enable interaction handlers",
     "fsExit.classList.remove('map-fs-show'); fsBtn.style.display = 'flex'; setTimeout(function(){ adsbMap.invalidateSize(); }, 60); };",
     "fsExit.classList.remove('map-fs-show'); fsBtn.style.display = 'flex'; " + REFIT + " };"),
    ("Refit on visualViewport resize while fullscreen (mobile toolbar)",
     "window.addEventListener('orientationchange', function(){ setTimeout(function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } }, 200); });",
     "window.addEventListener('orientationchange', function(){ setTimeout(function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } }, 200); });\n    if (window.visualViewport) { window.visualViewport.addEventListener('resize', function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } }); }"),
    ("Airport labels smaller (9px -> 7px)",
     "border: 1px solid #58a6ff; border-radius: 4px; padding: 1px 4px; font-size: 9px;",
     "border: 1px solid #58a6ff; border-radius: 3px; padding: 0 3px; font-size: 7px;"),
    ("Civic labels smaller (9px -> 7px)",
     "border: 1px solid #d29922; border-radius: 4px; padding: 1px 4px; font-size: 9px;",
     "border: 1px solid #d29922; border-radius: 3px; padding: 0 3px; font-size: 7px;"),
    ("Fire labels smaller (9px -> 7px)",
     "border: 1px solid #f85149; border-radius: 4px; padding: 1px 4px; font-size: 9px;",
     "border: 1px solid #f85149; border-radius: 3px; padding: 0 3px; font-size: 7px;"),
]

for desc, old, new in EDITS:
    n = src.count(old)
    if n != 1:
        print("PATCH ABORTED: %s: expected exactly 1 occurrence, found %d" % (desc, n))
        sys.exit(1)
    src = src.replace(old, new)
    print("ok: %s" % desc)

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
