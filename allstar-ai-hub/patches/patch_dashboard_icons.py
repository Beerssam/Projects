#!/usr/bin/env python3
"""Dashboard follow-up patch: airplane/helicopter map icons (by type, rotated by
heading), 75 NM range ring, and a working AMI log filter checkbox.
Target: /home/asl/ai_dashboard.py (already has the map upgrade patch).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_icons_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

AIRCRAFT_ICON_FN = """function aircraftIcon(a) {
    const cat = (a.category || '').toUpperCase();
    let emoji = '✈️';
    if (cat === 'A7') {
        emoji = '🚁';
    } else if (cat === 'A1' || cat === 'A2') {
        emoji = '🛩️';
    }
    let rot = '';
    if (emoji !== '🚁' && a.track !== null && a.track !== undefined) {
        rot = 'transform: rotate(' + Math.round(a.track) + 'deg);';
    }
    const halo = a.priority ? 'background: rgba(248,81,73,0.35); border-radius: 50%; padding: 2px;' : '';
    return L.divIcon({
        className: 'adsb-marker',
        html: '<span style="font-size: 22px; ' + rot + ' display: inline-block; ' + halo + '">' + emoji + '</span>',
        iconSize: [26, 26],
        iconAnchor: [13, 13]
    });
}
"""

AMI_FILTER_LISTENER = """    const _amiBox = document.getElementById('hide-ami');
    if (_amiBox) {
        _amiBox.addEventListener('change', function() {
            const hide = this.checked;
            document.querySelectorAll('#terminal .log-line').forEach(function(el) {
                if (el.textContent.indexOf('[AMI EVENT]') !== -1) {
                    el.style.display = hide ? 'none' : '';
                }
            });
        });
    }
"""

EDITS = [
    ("poller: include aircraft category for icon choice",
     '"dst": a.get("dst"),',
     '"dst": a.get("dst"),\n            "category": a.get("category"),'),
    ("CSS: transparent divIcon marker",
     "@media (min-width: 769px) {",
     ".adsb-marker { background: transparent; border: none; }\n@media (min-width: 769px) {"),
    ("map: 75 NM range ring",
     "    L.marker([38.99, -94.76]).addTo(adsbMap).bindPopup('KF0RIZ hub - Shawnee, KS');",
     "    L.marker([38.99, -94.76]).addTo(adsbMap).bindPopup('KF0RIZ hub - Shawnee, KS');\n    L.circle([38.99, -94.76], {radius: 138900, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap);"),
    ("JS: aircraftIcon function",
     "function pollAircraft() {",
     AIRCRAFT_ICON_FN + "function pollAircraft() {"),
    ("JS: drop unused color var",
     "            const color = a.priority ? '#f85149' : '#58a6ff';\n",
     ""),
    ("JS: marker uses aircraftIcon",
     "                const m = L.circleMarker([a.lat, a.lon], {radius: 6, color: color, fillColor: color, fillOpacity: 0.8}).addTo(adsbMap);",
     "                const m = L.marker([a.lat, a.lon], {icon: aircraftIcon(a)}).addTo(adsbMap);"),
    ("JS: AMI checkbox re-filters lines already shown",
     "    setInterval(pollPool, 15000);\n});",
     "    setInterval(pollPool, 15000);\n" + AMI_FILTER_LISTENER + "});"),
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
