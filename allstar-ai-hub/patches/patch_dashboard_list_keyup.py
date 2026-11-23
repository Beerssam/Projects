#!/usr/bin/env python3
"""Dashboard patch: aircraft list/table under the map (nearest 20) and a
LAST KEY-UP indicator in the AI SERVICE panel.
Target: /home/asl/ai_dashboard.py (map upgrade live; applies whether or not the
icons patch has been run -- all anchors are stable across both versions).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_list_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

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

EDITS = [
    ("CSS: aircraft list table",
     "</style>",
     LIST_CSS + "</style>"),
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
