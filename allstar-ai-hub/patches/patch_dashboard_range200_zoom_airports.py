#!/usr/bin/env python3
"""Dashboard: 200 NM range + metro default zoom + local airport pins, in one patch.
Sam has not run the range200 patch yet, so this does the range and the zoom
together, plus airport markers.
- Feed: dist 75 -> 200 (about 400 aircraft).
- Range ring: 138900 m (75 NM) -> 370400 m (200 NM).
- Title and poller comment: 75 -> 200 NM.
- Default zoom: set to 8 (Shawnee metro view) via regex, so it stays metro
  whether the current zoom is 7 or 8. The 200 NM data is still there; zoom
  out manually to see the farther planes.
- Airport pins: MCI, New Century, and Olathe Exec (Johnson County Exec)
  get a labelled pin on the map so you can see which airports traffic is
  coming to and from. Coordinates verified by geocoding.
Target: /home/asl/ai_dashboard.py with the map patch applied.
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
TMP = "/tmp/ai_dashboard_range200_zoom_airports_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("Feed: dist 75 -> 200",
     'ADSB_URL = "https://opendata.adsb.fi/api/v3/lat/38.9900/lon/-94.7600/dist/75"',
     'ADSB_URL = "https://opendata.adsb.fi/api/v3/lat/38.9900/lon/-94.7600/dist/200"'),
    ("Poller comment: 75 -> 200 NM",
     "# (75 NM around Shawnee) once a minute and keeps the latest aircraft list in",
     "# (200 NM around Shawnee) once a minute and keeps the latest aircraft list in"),
    ("Panel title: 75 -> 200 NM",
     '<div class="panel-title">LIVE AIRCRAFT - 75 NM AROUND SHAWNEE</div>',
     '<div class="panel-title">LIVE AIRCRAFT - 200 NM AROUND SHAWNEE</div>'),
    ("Range ring: 75 NM -> 200 NM",
     "L.circle([38.99, -94.76], {radius: 138900, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap);",
     "L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap);"),
    ("CSS: airport label style",
     ".ac-table tr.ac-pri td { color: #f85149; font-weight: bold; }",
     ".ac-table tr.ac-pri td { color: #f85149; font-weight: bold; }\n.ap-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #58a6ff; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap; }"),
    ("JS: local airport pins after the range ring",
     "L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap);",
     "L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap);\n    // Local airports: labelled pins so you can see where traffic is headed.\n    [{name: 'MCI', lat: 39.2982, lon: -94.71513}, {name: 'New Century', lat: 38.8389, lon: -94.89602}, {name: 'Olathe Exec', lat: 38.85441, lon: -94.73514}].forEach(function(ap){ L.marker([ap.lat, ap.lon], {icon: L.divIcon({className: 'ap-marker', html: '<div class=\"ap-label\">' + ap.name + '</div>', iconSize: null})}).addTo(adsbMap); });"),
]

for desc, old, new in EDITS:
    n = src.count(old)
    if n != 1:
        print("PATCH ABORTED: %s: expected exactly 1 occurrence, found %d" % (desc, n))
        sys.exit(1)
    src = src.replace(old, new)
    print("ok: %s" % desc)

# Default zoom to 8 (metro view) via regex, so it works whether it is 7 or 8 now.
pat = re.compile(r"(adsbMap = L\.map\('map'\)\.setView\(\[38\.99, -94\.76\], )(\d+)(\);)")
m = pat.search(src)
if not m:
    print("PATCH ABORTED: map setView line not found")
    sys.exit(1)
old_zoom = m.group(2)
src = pat.sub(r"\g<1>8\g<3>", src, count=1)
print("ok: default zoom %s -> 8 (Shawnee metro view)" % old_zoom)

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
