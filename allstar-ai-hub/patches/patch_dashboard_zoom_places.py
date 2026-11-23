#!/usr/bin/env python3
"""Dashboard: metro default zoom + labelled places on the map.
Sets the default zoom back to 8 (Shawnee metro view) and adds labelled pins
for local airports, Shawnee Police, Shawnee City Hall, and all four Shawnee
fire stations, so you can see where traffic is headed and where the city
services are.
Places (coordinates verified by geocoding / city sources):
- Airports: MCI, New Century, Olathe Exec, Downtown (KMKC), Lee's Summit (KLXT)
- Civic: Shawnee Police Dept (5850 Renner Rd), Shawnee City Hall (11110 Johnson Dr)
- Fire: Station 71 (6501 Quivira Rd), 72 (5840 Renner Rd),
  73 (6805 Hedge Lane Ter), 74 (5300 Woodsonia Dr)
Target: /home/asl/ai_dashboard.py with the 200 NM range already applied
(dist 200, ring 370400, title 200 NM, zoom 7).
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
TMP = "/tmp/ai_dashboard_zoom_places_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("CSS: place label styles",
     ".panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; margin-bottom: 15px; }",
     ".panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; margin-bottom: 15px; }\n.ap-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #58a6ff; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap; }\n.poi-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #d29922; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap; }\n.fire-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #f85149; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap; }"),
    ("JS: labelled places after the range ring",
     "L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap);",
     "L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap);\n    // Labelled places: airports, civic buildings, fire stations.\n    var PLACES = [\n        {name: 'MCI', lat: 39.2982, lon: -94.71513, cls: 'ap-label'},\n        {name: 'New Century', lat: 38.8389, lon: -94.89602, cls: 'ap-label'},\n        {name: 'Olathe Exec', lat: 38.85441, lon: -94.73514, cls: 'ap-label'},\n        {name: 'Downtown', lat: 39.13156, lon: -94.58741, cls: 'ap-label'},\n        {name: \"Lee's Summit\", lat: 38.96205, lon: -94.37537, cls: 'ap-label'},\n        {name: 'Shawnee PD', lat: 39.02386, lon: -94.78227, cls: 'poi-label'},\n        {name: 'Shawnee City Hall', lat: 39.0234, lon: -94.71521, cls: 'poi-label'},\n        {name: 'Fire 71', lat: 39.010516, lon: -94.722653, cls: 'fire-label'},\n        {name: 'Fire 72', lat: 39.023828, lon: -94.780433, cls: 'fire-label'},\n        {name: 'Fire 73', lat: 39.00577, lon: -94.85761, cls: 'fire-label'},\n        {name: 'Fire 74', lat: 39.0323, lon: -94.84965, cls: 'fire-label'}\n    ];\n    PLACES.forEach(function(p){ L.marker([p.lat, p.lon], {icon: L.divIcon({className: 'place-marker', html: '<div class=\"' + p.cls + '\">' + p.name + '</div>', iconSize: null})}).addTo(adsbMap); });"),
]

for desc, old, new in EDITS:
    n = src.count(old)
    if n != 1:
        print("PATCH ABORTED: %s: expected exactly 1 occurrence, found %d" % (desc, n))
        sys.exit(1)
    src = src.replace(old, new)
    print("ok: %s" % desc)

# Default zoom 7 -> 8 (Shawnee metro view).
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
