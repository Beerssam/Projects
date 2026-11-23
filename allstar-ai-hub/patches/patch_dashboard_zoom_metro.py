#!/usr/bin/env python3
"""Dashboard: default the map to the Shawnee metro view (zoom 8).
Keeps the 200 NM data feed and range ring, but loads the map zoomed in on
the Shawnee metro area instead of zoomed out to fit the whole 200 NM circle.
You can still zoom out manually to see the farther planes.
This sets the initial setView zoom to 8 regardless of its current value, so
it works whether or not the range200 patch has been run yet. It does not
touch the feed distance, the ring, or the title.
Target: /home/asl/ai_dashboard.py.
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if the map init line is missing.
"""
import os
import re
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_zoom_metro_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

pat = re.compile(r"(adsbMap = L\.map\('map'\)\.setView\(\[38\.99, -94\.76\], )(\d+)(\);)")
m = pat.search(src)
if not m:
    print("PATCH ABORTED: map setView line not found")
    sys.exit(1)
old_zoom = m.group(2)
src = pat.sub(r"\g<1>8\g<3>", src, count=1)
print("ok: initial map zoom %s -> 8 (Shawnee metro view, 200 NM data kept)" % old_zoom)

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: zoom set and syntax-checked.")
