#!/usr/bin/env python3
"""Dashboard v2 (supersedes patch_dashboard_icons.py and
patch_dashboard_list_keyup.py -- run THIS one instead, it has everything):
airplane/helicopter map icons (by ADS-B category, rotated by heading, red halo
for priority), 75 NM range ring, AMI checkbox that re-filters the log AND
remembers its on/off state across refreshes, aircraft list/table under the map
(nearest 20), LAST KEY-UP line, and the AI SERVICE panel moved up between the
header and the control buttons.
Target: /home/asl/ai_dashboard.py (map upgrade live; run this INSTEAD of the
two earlier follow-up patches, not on top of them).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_v2_patched.py"

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

LIST_CSS = """
.ac-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.ac-table th { color: #8b949e; text-align: left; padding: 4px 6px; border-bottom: 1px solid #30363d; font-family: sans-serif; font-size: 0.8rem; }
.ac-table td { padding: 4px 6px; border-bottom: 1px solid #161b22; color: #c9d1d9; }
.ac-table tr.ac-pri td { color: #f85149; font-weight: bold; }
#aircraft-list { max-height: 260px; overflow-y: auto; }
"""

LIST_PANEL = """
<div class="panel">
    <div class="panel-title">AIRCRAFT LIST - NEAREST FIRST</div>
    <div id="aircraft-list"><div class="qa-empty">Loading aircraft...</div></div>
</div>
"""

RENDER_FN = """function renderAircraftList(list) {
    const el = document.getElementById('aircraft-list');
    if (!el) return;
    if (!list || list.length === 0) {
        el.innerHTML = '<div class="qa-empty">No aircraft in range.</div>';
        return;
    }
    const sorted = list.slice().sort(function(x, y){ return (x.dst || 9999) - (y.dst || 9999); });
    const top = sorted.slice(0, 20);
    let html = '<table class="ac-table"><tr><th>CALLSIGN</th><th>TYPE</th><th>ALT</th><th>SPD</th><th>DIST</th></tr>';
    top.forEach(function(a){
        const cls = a.priority ? ' class="ac-pri"' : '';
        const dist = (a.dst !== null && a.dst !== undefined) ? Math.round(a.dst) + ' NM' : '-';
        html += '<tr' + cls + '><td>' + a.callsign + '</td><td>' + (a.type || '-') + '</td><td>' + fmtAlt(a.alt) + '</td><td>' + fmtSpd(a.spd) + '</td><td>' + dist + '</td></tr>';
    });
    html += '</table>';
    if (sorted.length > 20) {
        html += '<div class="adsb-updated">Showing nearest 20 of ' + sorted.length + ' aircraft.</div>';
    }
    el.innerHTML = html;
}
"""

# AI SERVICE panel as it sits inside the stat-grid (4-space outer indent).
AI_SERVICE_STAT = """    <div class="panel stat-box">
        <div class="panel-title">AI SERVICE</div>
        <div class="stat-line">STATUS: <b id="ai-status">...</b></div>
        <div class="stat-line">STARTED: <b id="ai-started">...</b></div>
        <div class="stat-line">LAST REPLY: <b id="ai-last-reply">...</b></div>
        <div class="stat-line">LAST KEY-UP: <b id="ai-last-keyup">...</b></div>
    </div>"""

# Same panel at top level (0-space outer indent) for its new home above the buttons.
AI_SERVICE_TOP = """<div class="panel stat-box">
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
    ("CSS: aircraft list table",
     "</style>",
     LIST_CSS + "</style>"),
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
    ("HTML: aircraft list panel after map",
     '    <div class="adsb-updated" id="adsb-updated">Loading aircraft...</div>\n</div>',
     '    <div class="adsb-updated" id="adsb-updated">Loading aircraft...</div>\n</div>\n' + LIST_PANEL.strip()),
    ("HTML: LAST KEY-UP line in AI SERVICE panel",
     '        <div class="stat-line">LAST REPLY: <b id="ai-last-reply">...</b></div>',
     '        <div class="stat-line">LAST REPLY: <b id="ai-last-reply">...</b></div>\n        <div class="stat-line">LAST KEY-UP: <b id="ai-last-keyup">...</b></div>'),
    ("JS: renderAircraftList function",
     "function pollAircraft() {",
     RENDER_FN + "function pollAircraft() {"),
    ("JS: render list on each aircraft poll",
     "        if (!adsbMap) return;",
     "        renderAircraftList(data.aircraft);\n        if (!adsbMap) return;"),
    ("JS: show last key-up in AI status",
     "        if (lr) lr.textContent = data.last_reply || '-';",
     "        if (lr) lr.textContent = data.last_reply || '-';\n        const lk = document.getElementById('ai-last-keyup');\n        if (lk) lk.textContent = data.last_keyup || '-';"),
    ("Python: ai_status returns last_keyup",
     '    return jsonify({"status": status, "started": started, "last_reply": last_reply})',
     '    last_keyup = ""\n    for line in reversed(_tail_log(300)):\n        if "[WHISPER GATE]" in line or "[RADIO INTERPRETATION]" in line:\n            last_keyup = _log_time(line)\n            break\n    return jsonify({"status": status, "started": started, "last_reply": last_reply, "last_keyup": last_keyup})'),
    ("layout: remove AI SERVICE panel from stat-grid",
     AI_SERVICE_STAT,
     ""),
    ("layout: AI SERVICE panel above the control buttons",
     "</header>\n\n<div class=\"control-panel\">",
     "</header>\n\n" + AI_SERVICE_TOP + "\n\n<div class=\"control-panel\">"),
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
