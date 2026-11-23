#!/usr/bin/env python3
"""Dashboard v3b (fix of v3): adds ONLY the pieces missing after the map + list
patches -- airplane/helicopter icons, 75 NM range ring, AMI checkbox that
re-filters the log AND remembers its on/off state across refreshes, and the
AI SERVICE panel moved up between the header and the control buttons.
Fixes v3's last edit: the live file has the header/control-panel indented
4 spaces (</header> then a 4-space "blank" line then the div), not at column 0.
Run THIS one. Do NOT re-run the map, icons, list, v2, or v3 patches.
Target: /home/asl/ai_dashboard.py with map + list patches already applied
(662 lines, AI SERVICE at line 228 inside the stat-grid).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_v3b_patched.py"

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

AMI_PERSIST = """const _amiBox = document.getElementById('hide-ami');
if (_amiBox) {
    const _savedAmi = localStorage.getItem('hide_ami');
    if (_savedAmi !== null) { _amiBox.checked = (_savedAmi === 'true'); }
    _amiBox.addEventListener('change', function() {
        localStorage.setItem('hide_ami', this.checked ? 'true' : 'false');
        const hide = this.checked;
        document.querySelectorAll('#terminal .log-line').forEach(function(el) {
            if (el.textContent.indexOf('[AMI EVENT]') !== -1) {
                el.style.display = hide ? 'none' : '';
            }
        });
    });
}
"""

# AI SERVICE panel (4-space outer indent). It sits inside the stat-grid now;
# its new home above the control buttons is also at 4 spaces, so the same
# text works for both the removal and the insertion.
AI_SERVICE_PANEL = """    <div class="panel stat-box">
        <div class="panel-title">AI SERVICE</div>
        <div class="stat-line">STATUS: <b id="ai-status">...</b></div>
        <div class="stat-line">STARTED: <b id="ai-started">...</b></div>
        <div class="stat-line">LAST REPLY: <b id="ai-last-reply">...</b></div>
        <div class="stat-line">LAST KEY-UP: <b id="ai-last-keyup">...</b></div>
    </div>"""

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
    ("JS: AMI checkbox restores saved state + re-filters on toggle",
     "const terminal = document.getElementById('terminal');",
     "const terminal = document.getElementById('terminal');\n" + AMI_PERSIST),
    ("layout: remove AI SERVICE panel from stat-grid",
     AI_SERVICE_PANEL,
     ""),
    ("layout: AI SERVICE panel above the control buttons",
     "    <div class=\"control-panel\">",
     AI_SERVICE_PANEL + "\n    \n    <div class=\"control-panel\">"),
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
