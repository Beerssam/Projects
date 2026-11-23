#!/usr/bin/env python3
"""Dashboard v4: fix the trail/projection lines + smaller tappable place labels
+ stop overlays blocking map pan/zoom.

Fixes Sam's 2026-11-23 17:23 CST report:
1. "The lines aren't showing" — ROOT CAUSE: /api/trail reads the aircraft
   speed as _ac.get('gs'), but the poller's aircraft dict stores speed as
   'spd' (there is no 'gs' key). So _gs was always None and the forward
   projection was always empty. The blue trail also needs 2+ fixes (60 s
   apart), so it only appears a couple of minutes after a restart.
   Fix: read 'spd' instead of 'gs'.
2. "Once you zoom in you can't move around or zoom out" — interactive
   overlays capture touches/drags. Fix: trail + projection polylines and
   the 200 NM ring are now interactive:false (they never need taps), and
   the place labels are made much smaller so they block far less of the
   map. (Labels stay tappable, per Sam's request below.)
3. "Make the building labels smaller and pop up bigger like the planes
   when tapped" — label text 11px -> 9px, padding 2px 6px -> 1px 4px;
   tapping a place marker now opens a popup with the name in large type.

Target: /home/asl/ai_dashboard.py (must already have trail3 applied).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import re
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_trail4_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("Projection speed field: 'gs' does not exist in the aircraft dict, use 'spd'",
     "_trk = _ac.get('track'); _gs = _ac.get('gs')",
     "_trk = _ac.get('track'); _gs = _ac.get('spd')"),
    ("Trail lookup: lowercase the hex so reg/callsign fallbacks still match",
     "def api_trail(hx):\n    _now = time.time()",
     "def api_trail(hx):\n    hx = (hx or '').lower()\n    _now = time.time()"),
    ("JS: lowercase the hex before fetching trail/route",
     "var hx = ac.hex || ac.reg || ac.callsign;",
     "var hx = (ac.hex || ac.reg || ac.callsign || '').toLowerCase();"),
    ("Trail polyline must not block map pan/zoom",
     "L.polyline(d.trail, {color: '#58a6ff', weight: 3})",
     "L.polyline(d.trail, {color: '#58a6ff', weight: 3, interactive: false})"),
    ("Forward polyline must not block map pan/zoom",
     "L.polyline(fp, {color: '#3fb950', weight: 3, dashArray: '6 6'})",
     "L.polyline(fp, {color: '#3fb950', weight: 3, dashArray: '6 6', interactive: false})"),
    ("200 NM ring must not block map pan/zoom",
     "L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'})",
     "L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6', interactive: false})"),
    ("Airport labels smaller (11px -> 9px)",
     "border: 1px solid #58a6ff; border-radius: 4px; padding: 2px 6px; font-size: 11px;",
     "border: 1px solid #58a6ff; border-radius: 4px; padding: 1px 4px; font-size: 9px;"),
    ("Civic labels smaller (11px -> 9px)",
     "border: 1px solid #d29922; border-radius: 4px; padding: 2px 6px; font-size: 11px;",
     "border: 1px solid #d29922; border-radius: 4px; padding: 1px 4px; font-size: 9px;"),
    ("Fire labels smaller (11px -> 9px)",
     "border: 1px solid #f85149; border-radius: 4px; padding: 2px 6px; font-size: 11px;",
     "border: 1px solid #f85149; border-radius: 4px; padding: 1px 4px; font-size: 9px;"),
    ("Tap a place label -> popup with the name big",
     "iconAnchor: anch})}).addTo(adsbMap);});",
     "iconAnchor: anch})}).addTo(adsbMap).bindPopup('<div style=\"font-size:20px;font-weight:bold;\">' + p.name + '</div><div style=\"font-size:13px;color:#8b949e;\">' + (p.cls === 'fire-label' ? 'Fire Station' : (p.cls === 'ap-label' ? 'Airport' : (p.name.indexOf('PD') !== -1 ? 'Police Department' : 'City Hall'))) + '</div>');});"),
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
