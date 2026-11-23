#!/usr/bin/env python3
"""Dashboard: expand the ADS-B map range from 75 NM to 200 NM.
The dashboard ADS-B feed is separate from the AI orchestrator's feed, so
widening the map does not add any load to Gemini. Changes:
- ADSB_URL dist 75 -> 200 (the feed now returns ~400 aircraft).
- Range ring radius 138900 m (75 NM) -> 370400 m (200 NM).
- Initial map zoom 8 -> 7 so the wider circle fits on screen.
- Panel title and poller comment updated to 200 NM.
Target: /home/asl/ai_dashboard.py with the map patch applied.
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_range200_patched.py"

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
    ("Initial map zoom 8 -> 7 for the wider view",
     "adsbMap = L.map('map').setView([38.99, -94.76], 8);",
     "adsbMap = L.map('map').setView([38.99, -94.76], 7);"),
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
