#!/usr/bin/env python3
"""Dashboard trail/forward: make the lines longer and easier to see.

Sam (2026-11-23 18:03 CST): tapping a plane shows a blue line and a
dotted line, but both are tiny -- just a stub right in front of the plane.
They don't show where it's been or where it's going.

Two reasons:
1. The blue trail only keeps 15 min of fixes, and the service was just
   restarted, so it only had ~2 min of history. Keep 30 min instead.
2. The green forward projection only goes to +10 min. At the default
   200 NM map view a +10 min line is a small stub, especially for a slow
   plane. Extend it to +30 min so it reads clearly at any zoom.
   (The projection math itself is verified correct: a 400 kt airliner
   is 66.7 NM ahead at +10 min, a 60 kt helicopter 10 NM.)

Changes:
- Trail window 900 s (15 min) -> 1800 s (30 min), in both the recorder
  and the /api/trail filter. Still capped at the last 30 fixes.
- Forward points (2, 5, 10) min -> (5, 10, 20, 30) min.
- Both polylines weight 3 -> 4 so they read better on a phone.

Target: /home/asl/ai_dashboard.py (must have trail3 + trail4b).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_trail5_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("Trail recorder: keep 30 min of fixes (was 15 min)",
     "_trail[_hx] = [p for p in _lst if _now - p[2] <= 900][-30:]",
     "_trail[_hx] = [p for p in _lst if _now - p[2] <= 1800][-30:]"),
    ("Trail API: return 30 min of fixes (was 15 min)",
     "_pts = [[p[0], p[1]] for p in _trail.get(hx, []) if _now - p[2] <= 900]",
     "_pts = [[p[0], p[1]] for p in _trail.get(hx, []) if _now - p[2] <= 1800]"),
    ("Forward projection: extend to +30 min (was +10 min)",
     "for _mins in (2, 5, 10):",
     "for _mins in (5, 10, 20, 30):"),
    ("Trail polyline thicker (3 -> 4)",
     "L.polyline(d.trail, {color: '#58a6ff', weight: 3, interactive: false})",
     "L.polyline(d.trail, {color: '#58a6ff', weight: 4, interactive: false})"),
    ("Forward polyline thicker (3 -> 4)",
     "L.polyline(fp, {color: '#3fb950', weight: 3, dashArray: '6 6', interactive: false})",
     "L.polyline(fp, {color: '#3fb950', weight: 4, dashArray: '6 6', interactive: false})"),
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
