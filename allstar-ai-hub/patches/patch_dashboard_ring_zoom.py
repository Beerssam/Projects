#!/usr/bin/env python3
"""Dashboard: stop the 200 NM ring freezing the page at max zoom.

Sam (2026-11-23 18:01 CST): ran fullscreen_fix2, tested on the MAIN page
(not fullscreen) -- zooming in all the way locked up the ENTIRE dashboard:
couldn't move the map, couldn't scroll the page, couldn't zoom out,
nothing responding. So it is NOT fullscreen-only.

Root cause: the 200 NM range ring is a Leaflet L.circle with radius
370400 m. At max zoom (z19) that circle is ~1.2 MILLION pixels across
on screen. Leaflet renders it as one giant SVG path, and the browser
chokes trying to draw it -- the main thread blocks, so the whole page
(including scrolling) freezes. It only bites at high zoom, which is why
zooming in all the way triggers it. The ring is only useful zoomed out
anyway (you can't see a 200 NM circle when zoomed into a neighborhood).

Fix: keep the ring, but only show it at zoom 12 or below. Above zoom 12
it is removed from the map (and re-added when you zoom back out), via a
zoomend handler. The ring variable is stored so it can be toggled.

Target: /home/asl/ai_dashboard.py (must have trail4b / fullscreen_fix2).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if the anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_ringzoom_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

OLD = ("L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, "
       "fill: false, dashArray: '6 6', interactive: false}).addTo(adsbMap);")
NEW = ("var rangeRing = L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, "
       "fill: false, dashArray: '6 6', interactive: false}).addTo(adsbMap);\n"
       "    function _toggleRing(){ if (adsbMap.getZoom() > 12) { if (adsbMap.hasLayer(rangeRing)) adsbMap.removeLayer(rangeRing); } "
       "else { if (!adsbMap.hasLayer(rangeRing)) rangeRing.addTo(adsbMap); } }\n"
       "    adsbMap.on('zoomend', _toggleRing); _toggleRing();")

n = src.count(OLD)
if n != 1:
    print("PATCH ABORTED: 200 NM ring line: expected exactly 1 occurrence, found %d" % n)
    sys.exit(1)
src = src.replace(OLD, NEW)
print("ok: 200 NM ring hidden above zoom 12 (was freezing the page at max zoom)")

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
