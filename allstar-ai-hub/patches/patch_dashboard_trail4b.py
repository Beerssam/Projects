#!/usr/bin/env python3
"""Dashboard v4b: corrected v4 (v4 aborted on its last edit).
v4's 10th edit anchored on the exact tail "iconAnchor: anch})}).addTo(adsbMap);});"
but the live file's PLACES loop is formatted differently, so it matched 0
times and the whole patch aborted safely (nothing changed). This v4b keeps
v4's 9 proven edits and replaces the 10th with a regex that finds the
PLACES loop's marker no matter how its closing braces are laid out.

Fixes Sam's 2026-11-23 17:23 CST report:
1. "The lines aren't showing" — /api/trail read speed as _ac.get('gs')
   but the aircraft dict stores it as 'spd' (no 'gs' key), so the forward
   projection was always empty. Fix: read 'spd'.
2. "Can't move around or zoom out after zooming in" — interactive
   overlays capture touches/drags. Trail + projection polylines and the
   200 NM ring are now interactive:false; place labels are much smaller.
3. "Building labels smaller, pop up bigger like planes when tapped" —
   label text 11px -> 9px, padding 2px 6px -> 1px 4px; tapping a place
   marker opens a popup with the name in large type.

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
TMP = "/tmp/ai_dashboard_trail4b_patched.py"

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
]

for desc, old, new in EDITS:
    n = src.count(old)
    if n != 1:
        print("PATCH ABORTED: %s: expected exactly 1 occurrence, found %d" % (desc, n))
        sys.exit(1)
    src = src.replace(old, new)
    print("ok: %s" % desc)

# 10th edit (regex): tap a place label -> popup with the name big.
# Anchors on "PLACES.forEach(function(p){" and the FIRST ".addTo(adsbMap)"
# after it (the PLACES marker), tolerating any whitespace/newlines in
# between. Inserts .bindPopup(...) right after .addTo(adsbMap).
_pat = re.compile(r"(PLACES\.forEach\(function\(p\)\{.*?\.addTo\(adsbMap\))(\s*;)", re.DOTALL)
_matches = _pat.findall(src)
if len(_matches) != 1:
    print("PATCH ABORTED: place-label popup (regex): expected exactly 1 occurrence, found %d" % len(_matches))
    sys.exit(1)
_popup = (".bindPopup('<div style=\"font-size:20px;font-weight:bold;\">' + p.name + '</div>'"
          " + '<div style=\"font-size:13px;color:#8b949e;\">'"
          " + (p.cls === 'fire-label' ? 'Fire Station' : (p.cls === 'ap-label' ? 'Airport' : (p.name.indexOf('PD') !== -1 ? 'Police Department' : 'City Hall')))"
          " + '</div>')")
src = _pat.sub(lambda m: m.group(1) + _popup + m.group(2), src, count=1)
print("ok: Tap a place label -> popup with the name big")

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
