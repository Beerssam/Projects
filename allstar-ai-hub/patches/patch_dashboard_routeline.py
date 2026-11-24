#!/usr/bin/env python3
"""Dashboard: draw the flight route on the map when you tap a plane.

- Adds AIRPORT_COORDS (IATA -> [lat, lon]) for major US airports + local fields.
- In the click handler, after the trail/forward lines, draws:
  - origin -> plane: solid amber line (where it came from)
  - plane -> destination: dashed blue line (where it is going)
  Uses rt.origin / rt.destination from /api/route (AviationStack live first,
  OpenSky fallback). If an airport is not in the dictionary, that segment is
  skipped gracefully (popup text still shows the route).
- Route lines are removed when another plane is tapped (same as trail/fwd).
- Lines are non-interactive so they never block map pan/zoom.
- Requires backup /home/asl/backups/20261123/ai_dashboard.py to exist.
- Writes via temp file + py_compile + shutil.copyfile; aborts safely if any
  anchor is not found exactly once.
"""
import os
import sys
import shutil
import py_compile
import re

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_routeline.py"

if not os.path.isfile(BACKUP):
    print("PATCH ABORTED: backup %s not found; refusing to edit live file" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

# --- Edit 1: AIRPORT_COORDS dictionary, inserted before the click-handler IIFE.
# Anchor on the marker-assignment line (same regex trail3 used; proven to match).
_pat = re.compile(r"(?m)^(\s*)adsbMarkers\[key\] = m;\s*$")
_matches = _pat.findall(src)
if len(_matches) != 1:
    print("PATCH ABORTED: JS marker line: expected exactly 1 occurrence, found %d" % len(_matches))
    sys.exit(1)
_indent = _matches[0]
_coords = (
    _indent + "var AIRPORT_COORDS = {\n"
    + _indent + "    'ATL': [33.6407, -84.4277], 'LAX': [33.9416, -118.4085], 'ORD': [41.9742, -87.9073],\n"
    + _indent + "    'DFW': [32.8998, -97.0403], 'DEN': [39.8561, -104.6737], 'JFK': [40.6413, -73.7781],\n"
    + _indent + "    'SFO': [37.6213, -122.3790], 'SEA': [47.4502, -122.3088], 'LAS': [36.0840, -115.1537],\n"
    + _indent + "    'MCO': [28.4312, -81.3081], 'EWR': [40.6895, -74.1745], 'CLT': [35.2144, -80.9473],\n"
    + _indent + "    'MIA': [25.7959, -80.2870], 'PHX': [33.4373, -112.0078], 'IAH': [29.9902, -95.3368],\n"
    + _indent + "    'BOS': [42.3656, -71.0096], 'MSP': [44.8848, -93.2223], 'DTW': [42.2124, -83.3534],\n"
    + _indent + "    'PHL': [39.8744, -75.2424], 'LGA': [40.7769, -73.8740], 'BWI': [39.1754, -76.6684],\n"
    + _indent + "    'SLC': [40.7899, -111.9791], 'SAN': [32.7338, -117.1933], 'IAD': [38.9531, -77.4565],\n"
    + _indent + "    'DCA': [38.8512, -77.0402], 'MDW': [41.7868, -87.7522], 'TPA': [27.9755, -82.5332],\n"
    + _indent + "    'PDX': [45.5898, -122.5951], 'STL': [38.7487, -90.3700], 'BNA': [36.1263, -86.6774],\n"
    + _indent + "    'AUS': [30.1975, -97.6664], 'MSY': [29.9934, -90.2580], 'RDU': [35.8776, -78.7875],\n"
    + _indent + "    'SMF': [38.6954, -121.5908], 'MCI': [39.2982, -94.7151], 'MEM': [35.0424, -89.9767],\n"
    + _indent + "    'OMA': [41.3032, -95.8941], 'DSM': [41.5340, -93.6631], 'ICT': [37.6499, -97.4331],\n"
    + _indent + "    'TUL': [36.1984, -95.8881], 'OKC': [35.3931, -97.6007], 'SNA': [33.6757, -117.8682],\n"
    + _indent + "    'HYS': [38.8440, -99.2738], 'IXD': [38.8389, -94.8960], 'OJC': [38.8544, -94.7351],\n"
    + _indent + "    'MKC': [39.1316, -94.5874], 'LXT': [38.9621, -94.3754], 'CMH': [39.9980, -82.8919],\n"
    + _indent + "    'IND': [39.7173, -86.2944], 'PIT': [40.4915, -80.2329], 'CLE': [41.4117, -81.8498],\n"
    + _indent + "    'LIT': [34.7294, -92.2243], 'HSV': [34.6372, -86.7751], 'BHM': [33.5629, -86.7535],\n"
    + _indent + "    'GSO': [36.0978, -79.9373], 'RIC': [37.5052, -77.3197], 'ORF': [36.8946, -76.2012],\n"
    + _indent + "    'PVD': [41.7240, -71.4282], 'ALB': [42.7483, -73.8017], 'BUF': [42.9405, -78.7322],\n"
    + _indent + "    'ROC': [43.1189, -77.6724], 'SYR': [43.1112, -76.1063], 'GRR': [42.8808, -85.5228],\n"
    + _indent + "    'MSN': [43.1399, -89.3375]\n"
    + _indent + "};\n"
)
src = _pat.sub(lambda m: m.group(0) + "\n" + _coords, src, count=1)
print("ok: AIRPORT_COORDS dictionary before click handler")

# --- Edit 2: draw route lines after the forward polyline.
# Anchor on the forward polyline line (current text after trail4+trail5:
# weight 4, dashArray, interactive false). Capture leading whitespace so the
# added lines match the surrounding indentation.
_pat2 = re.compile(
    r"(?m)^(\s*)if \(d\.forward && d\.forward\.length > 0\) \{ var fp = \[\[ac\.lat, ac\.lon\]\]\.concat\(d\.forward\); "
    r"adsbMap\._fwdLine = L\.polyline\(fp, \{color: '#3fb950', weight: 4, dashArray: '6 6', interactive: false\}\)\.addTo\(adsbMap\); \}\s*$"
)
_m2 = _pat2.search(src)
if not _m2:
    print("PATCH ABORTED: forward polyline line: expected exactly 1 occurrence, found 0")
    sys.exit(1)
_ind2 = _m2.group(1)
_route_js = (
    "\n" + _ind2 + "        if (adsbMap._routeFromLine) { adsbMap.removeLayer(adsbMap._routeFromLine); adsbMap._routeFromLine = null; }\n"
    + _ind2 + "        if (adsbMap._routeToLine) { adsbMap.removeLayer(adsbMap._routeToLine); adsbMap._routeToLine = null; }\n"
    + _ind2 + "        if (rt.origin && rt.destination) {\n"
    + _ind2 + "            var _oc = AIRPORT_COORDS[rt.origin], _dc = AIRPORT_COORDS[rt.destination];\n"
    + _ind2 + "            if (_oc) { adsbMap._routeFromLine = L.polyline([_oc, [ac.lat, ac.lon]], {color: '#e3b341', weight: 3, interactive: false}).addTo(adsbMap); }\n"
    + _ind2 + "            if (_dc) { adsbMap._routeToLine = L.polyline([[ac.lat, ac.lon], _dc], {color: '#58a6ff', weight: 3, dashArray: '8 6', interactive: false}).addTo(adsbMap); }\n"
    + _ind2 + "        }"
)
src = _pat2.sub(lambda m: m.group(0) + _route_js, src, count=1)
print("ok: draw origin->plane and plane->destination route lines")

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
