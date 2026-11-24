#!/usr/bin/env python3
"""Dashboard: focus mode when you tap a plane.

- When you tap a plane, all OTHER plane markers fade to ~12% opacity
  (not fully gone, so the context is still there) while the selected
  plane stays full brightness, so its trail + forward + route lines
  are easy to trace without clutter.
- Tap the map background (or tap another plane) and everything comes
  back to full opacity and the focus lines clear.
- A 300 ms guard ignores the map-click that propagates right after a
  marker tap, so tapping a plane does not instantly unfocus it.
- Markers use setOpacity (works on the divIcon markers); lines are
  non-interactive so they never block pan/zoom.
- Requires backup /home/asl/backups/20261123/ai_dashboard.py to exist.
- Writes via temp file + py_compile + shutil.copyfile; aborts safely if
  any anchor is not found exactly once. Requires the route-line patch
  (patch_dashboard_routeline.py) to already be applied, since Edit 1
  anchors on its removal line.
"""
import os
import sys
import shutil
import py_compile
import re

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_focus.py"

if not os.path.isfile(BACKUP):
    print("PATCH ABORTED: backup %s not found; refusing to edit live file" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

# --- Edit 1: dim other markers when a plane is tapped.
# Anchor on the route-line removal line (added by the routeline patch).
# Capture its leading whitespace so the new lines match the indent.
_pat = re.compile(
    r"(?m)^(\s*)if \(adsbMap\._routeFromLine\) \{ adsbMap\.removeLayer\(adsbMap\._routeFromLine\); adsbMap\._routeFromLine = null; \}\s*$"
)
_m = _pat.search(src)
if not _m:
    print("PATCH ABORTED: route-line removal line: expected exactly 1 occurrence, found 0 (run patch_dashboard_routeline.py first)")
    sys.exit(1)
_ind = _m.group(1)
_focus = (
    _ind + "adsbMap._lastMkClick = Date.now();\n"
    + _ind + "Object.keys(adsbMarkers).forEach(function(k){ if (adsbMarkers[k] !== mk) { adsbMarkers[k].setOpacity(0.12); } else { adsbMarkers[k].setOpacity(1); } });\n"
)
src = _pat.sub(lambda m: _focus + m.group(0), src, count=1)
print("ok: dim other markers on tap")

# --- Edit 2: map click restores everything.
# Anchor on the map creation line; insert the click handler after it.
_pat2 = re.compile(r"(?m)^(\s*)adsbMap = L\.map\('map'.*$")
_m2 = _pat2.search(src)
if not _m2:
    print("PATCH ABORTED: map creation line: expected exactly 1 occurrence, found 0")
    sys.exit(1)
_ind2 = _m2.group(1)
_handler = (
    "\n" + _ind2 + "adsbMap.on('click', function(){\n"
    + _ind2 + "    if (Date.now() - (adsbMap._lastMkClick || 0) < 300) return;\n"
    + _ind2 + "    Object.keys(adsbMarkers).forEach(function(k){ adsbMarkers[k].setOpacity(1); });\n"
    + _ind2 + "    if (adsbMap._routeFromLine) { adsbMap.removeLayer(adsbMap._routeFromLine); adsbMap._routeFromLine = null; }\n"
    + _ind2 + "    if (adsbMap._routeToLine) { adsbMap.removeLayer(adsbMap._routeToLine); adsbMap._routeToLine = null; }\n"
    + _ind2 + "    if (adsbMap._trailLine) { adsbMap.removeLayer(adsbMap._trailLine); adsbMap._trailLine = null; }\n"
    + _ind2 + "    if (adsbMap._fwdLine) { adsbMap.removeLayer(adsbMap._fwdLine); adsbMap._fwdLine = null; }\n"
    + _ind2 + "});"
)
src = _pat2.sub(lambda m: m.group(0) + _handler, src, count=1)
print("ok: map click restores all markers and clears focus lines")

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
print("Restart the dashboard: sudo systemctl restart ai_dashboard.service")
