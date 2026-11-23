#!/usr/bin/env python3
"""Dashboard extras: tap an aircraft row to focus the map, plus a HUB HEALTH panel.
Feature A (map tap): aircraft list rows become clickable (when the aircraft
has lat/lon). Tapping a row centers the map on that aircraft and opens its
popup. Rows get a pointer cursor and a hover highlight.
Feature B (hub health): a new HUB HEALTH panel showing Pi temperature, 1-min
load, uptime, and disk free, polled every 30 s from a new /api/health route.
Uses os (already imported) and plain file reads; no new imports.
Target: /home/asl/ai_dashboard.py with the map+list+v3b patches applied.
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_extras_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("CSS: clickable aircraft rows",
     """.ac-table tr.ac-pri td { color: #f85149; font-weight: bold; }""",
     """.ac-table tr.ac-pri td { color: #f85149; font-weight: bold; }
.ac-table tr[data-lat] { cursor: pointer; }
.ac-table tr[data-lat]:hover td { background: #21262d; }"""),

    ("List rows: tap to focus map",
     """        html += '<tr' + cls + '><td>' + a.callsign + '</td><td>' + (a.type || '-') + '</td><td>' + fmtAlt(a.alt) + '</td><td>' + fmtSpd(a.spd) + '</td><td>' + dist + '</td></tr>';""",
     """        const mkey = a.reg || a.callsign;
        const clickable = (a.lat !== null && a.lat !== undefined && a.lon !== null && a.lon !== undefined) ? ' data-lat="' + a.lat + '" data-lon="' + a.lon + '" data-key="' + mkey + '" onclick="focusAircraft(this)" title="Tap to show on map"' : '';
        html += '<tr' + cls + clickable + '><td>' + a.callsign + '</td><td>' + (a.type || '-') + '</td><td>' + fmtAlt(a.alt) + '</td><td>' + fmtSpd(a.spd) + '</td><td>' + dist + '</td></tr>';"""),

    ("JS: focusAircraft + fmtUptime + pollHealth",
     """function aircraftIcon(a) {""",
     """function focusAircraft(row) {
    const lat = parseFloat(row.getAttribute('data-lat'));
    const lon = parseFloat(row.getAttribute('data-lon'));
    const key = row.getAttribute('data-key');
    if (isNaN(lat) || isNaN(lon) || !adsbMap) return;
    adsbMap.setView([lat, lon], Math.max(adsbMap.getZoom(), 10));
    if (key && adsbMarkers[key]) { adsbMarkers[key].openPopup(); }
}
function fmtUptime(s) {
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d > 0) return d + 'd ' + h + 'h';
    if (h > 0) return h + 'h ' + m + 'm';
    return m + 'm';
}
function pollHealth() {
    fetch('/api/health').then(function(r){ return r.json(); }).then(function(d){
        const el = document.getElementById('hub-health');
        if (!el) return;
        const temp = (d.temp_c !== null && d.temp_c !== undefined) ? d.temp_c.toFixed(1) + '\\u00b0C' : '-';
        const load = (d.load1 !== null && d.load1 !== undefined) ? d.load1.toFixed(2) : '-';
        const up = (d.uptime_s !== null && d.uptime_s !== undefined) ? fmtUptime(d.uptime_s) : '-';
        const disk = (d.disk_free_gb !== null && d.disk_free_gb !== undefined) ? Math.round(d.disk_free_gb) + ' GB free' : '-';
        el.textContent = 'TEMP ' + temp + '  |  LOAD ' + load + '  |  UP ' + up + '  |  DISK ' + disk;
    }).catch(function(){});
}
function aircraftIcon(a) {"""),

    ("HTML: HUB HEALTH panel before control buttons",
     """    <div class="control-panel">""",
     """    <div class="panel">
        <div class="panel-title">HUB HEALTH</div>
        <div class="stat-line" id="hub-health">Loading...</div>
    </div>
    <div class="control-panel">"""),

    ("JS: poll health on load and every 30s",
     """    setInterval(pollPool, 15000);""",
     """    setInterval(pollPool, 15000);
    pollHealth();
    setInterval(pollHealth, 30000);"""),

    ("Python: /api/health route",
     """@app.route('/stream')""",
     """@app.route('/api/health')
def health():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            temp_c = int(f.read().strip()) / 1000.0
    except Exception:
        temp_c = None
    try:
        load1 = os.getloadavg()[0]
    except Exception:
        load1 = None
    try:
        with open('/proc/uptime') as f:
            up_s = float(f.read().split()[0])
    except Exception:
        up_s = None
    try:
        st = os.statvfs('/')
        disk_free_gb = (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except Exception:
        disk_free_gb = None
    return jsonify({'temp_c': temp_c, 'load1': load1, 'uptime_s': up_s, 'disk_free_gb': disk_free_gb})

@app.route('/stream')"""),
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
