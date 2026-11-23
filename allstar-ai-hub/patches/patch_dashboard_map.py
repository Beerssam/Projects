#!/usr/bin/env python3
"""Dashboard upgrade patch: live ADS-B map, recent Q&A, AI status, Gemini pool
health, cleaner log filter, mobile-first responsive layout.
Target: /home/asl/ai_dashboard.py (313 lines, 15407 bytes).
Backup required: /home/asl/backups/20261123/ai_dashboard.py (verified identical
by diff before this patch was written).
Applies edits, syntax-checks, then copies into place. Aborts safely if any
anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

# ---------------- inserted CSS (before </style>) ----------------
NEW_CSS = """
/* --- DASHBOARD UPGRADE: MAP / STATUS / Q&A PANELS --- */
.panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; margin-bottom: 15px; }
.panel-title { color: #58a6ff; font-weight: bold; font-size: 0.95rem; letter-spacing: 0.5px; margin-bottom: 10px; font-family: sans-serif; }
#map { height: 320px; width: 100%; border-radius: 6px; border: 1px solid #30363d; background: #010409; z-index: 1; }
.adsb-stats { display: flex; gap: 16px; flex-wrap: wrap; color: #8b949e; font-size: 0.85rem; font-weight: bold; margin-bottom: 10px; }
.adsb-stats b { color: #e3b341; }
.adsb-updated { color: #8b949e; font-size: 0.8rem; margin-top: 8px; }
.stat-grid { display: grid; grid-template-columns: 1fr; gap: 15px; margin-bottom: 15px; }
.stat-box { margin-bottom: 0; }
.stat-line { color: #c9d1d9; font-size: 0.9rem; margin: 4px 0; }
.stat-line b { color: #7fe7c4; }
.qa-item { border-bottom: 1px solid #161b22; padding: 8px 0; }
.qa-item:last-child { border-bottom: none; }
.qa-q { color: #58a6ff; font-size: 0.9rem; }
.qa-a { color: #c9d1d9; font-size: 0.9rem; }
.qa-time { color: #8b949e; font-size: 0.8rem; }
.qa-empty { color: #8b949e; font-size: 0.9rem; }
.filter-row { display: flex; align-items: center; gap: 8px; color: #8b949e; font-size: 0.85rem; font-family: sans-serif; margin-bottom: 8px; }
.filter-row input { width: 18px; height: 18px; }
@media (min-width: 769px) {
    body { max-width: 1100px; margin: 0 auto; }
    #map { height: 420px; }
    #terminal { height: 420px; }
    .stat-grid { grid-template-columns: 1fr 1fr; }
}
"""

# ---------------- Leaflet CDN (before </head>) ----------------
LEAFLET_CDN = """<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
"""

# ---------------- new HTML panels (replaces the lone terminal div) ----------------
NEW_PANELS = """
<div class="panel">
    <div class="panel-title">LIVE AIRCRAFT - 75 NM AROUND SHAWNEE</div>
    <div class="adsb-stats">
        <span>AIRCRAFT IN RANGE: <b id="adsb-count">...</b></span>
        <span>NEAREST: <b id="adsb-nearest">...</b></span>
        <span>PRIORITY: <b id="adsb-priority">...</b></span>
    </div>
    <div id="map"></div>
    <div class="adsb-updated" id="adsb-updated">Loading aircraft...</div>
</div>

<div class="stat-grid">
    <div class="panel stat-box">
        <div class="panel-title">AI SERVICE</div>
        <div class="stat-line">STATUS: <b id="ai-status">...</b></div>
        <div class="stat-line">STARTED: <b id="ai-started">...</b></div>
        <div class="stat-line">LAST REPLY: <b id="ai-last-reply">...</b></div>
    </div>
    <div class="panel stat-box">
        <div class="panel-title">GEMINI POOL</div>
        <div class="stat-line">ACTIVE KEY: <b id="pool-key">...</b></div>
        <div class="stat-line">RECENT REPLIES: <b id="pool-calls">...</b></div>
        <div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div>
    </div>
</div>

<div class="panel">
    <div class="panel-title">RECENT QUESTIONS &amp; ANSWERS</div>
    <div id="qa-list"><div class="qa-empty">Loading...</div></div>
</div>

<div class="filter-row"><label><input type="checkbox" id="hide-ami" checked> Hide AMI events in log</label></div>
<div id="terminal"></div>
"""

# ---------------- new JS (before </script>) ----------------
NEW_JS = """
// --- DASHBOARD UPGRADE: MAP / STATUS / Q&A ---
let adsbMap = null;
let adsbMarkers = {};
function initAdsbMap() {
    if (typeof L === 'undefined') return;
    if (!document.getElementById('map')) return;
    adsbMap = L.map('map').setView([38.99, -94.76], 8);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 12, attribution: '&copy; OpenStreetMap contributors'}).addTo(adsbMap);
    L.marker([38.99, -94.76]).addTo(adsbMap).bindPopup('KF0RIZ hub - Shawnee, KS');
}
function fmtAlt(a) {
    if (a === null || a === undefined) return 'n/a';
    return Math.round(a).toLocaleString() + ' ft';
}
function fmtSpd(s) {
    if (s === null || s === undefined) return 'n/a';
    return Math.round(s) + ' kt';
}
function pollAircraft() {
    fetch('/api/aircraft').then(function(res){ return res.json(); }).then(function(data){
        const countEl = document.getElementById('adsb-count');
        if (countEl) countEl.textContent = data.count;
        const nearEl = document.getElementById('adsb-nearest');
        if (nearEl) nearEl.textContent = data.nearest ? (data.nearest.callsign + ' (' + Math.round(data.nearest.dst) + ' NM)') : 'none';
        const priEl = document.getElementById('adsb-priority');
        if (priEl) priEl.textContent = data.priority_count;
        const updEl = document.getElementById('adsb-updated');
        if (updEl) updEl.textContent = data.updated_str ? ('Updated ' + data.updated_str) : 'Waiting for first poll...';
        if (!adsbMap) return;
        const seen = {};
        data.aircraft.forEach(function(a){
            const key = a.reg || a.callsign;
            seen[key] = true;
            const color = a.priority ? '#f85149' : '#58a6ff';
            const popup = '<b>' + a.callsign + '</b><br>' + (a.reg || '') + ' ' + (a.type || '') + '<br>Alt ' + fmtAlt(a.alt) + ' - ' + fmtSpd(a.spd) + (a.priority ? '<br><b>PRIORITY</b>' : '');
            if (adsbMarkers[key]) {
                adsbMarkers[key].setLatLng([a.lat, a.lon]);
                adsbMarkers[key].setPopupContent(popup);
            } else {
                const m = L.circleMarker([a.lat, a.lon], {radius: 6, color: color, fillColor: color, fillOpacity: 0.8}).addTo(adsbMap);
                m.bindPopup(popup);
                adsbMarkers[key] = m;
            }
        });
        Object.keys(adsbMarkers).forEach(function(k){
            if (!seen[k]) { adsbMap.removeLayer(adsbMarkers[k]); delete adsbMarkers[k]; }
        });
    }).catch(function(){});
}
function pollRecent() {
    fetch('/api/recent').then(function(res){ return res.json(); }).then(function(data){
        const list = document.getElementById('qa-list');
        if (!list) return;
        if (!data.items || data.items.length === 0) {
            list.innerHTML = '<div class="qa-empty">No questions yet in this log window.</div>';
            return;
        }
        list.innerHTML = data.items.map(function(it){
            return '<div class="qa-item"><div class="qa-time">' + it.time + '</div><div class="qa-q">Q: ' + it.q + '</div><div class="qa-a">A: ' + it.a + '</div></div>';
        }).join('');
    }).catch(function(){});
}
function pollAiStatus() {
    fetch('/api/ai_status').then(function(res){ return res.json(); }).then(function(data){
        const s = document.getElementById('ai-status');
        if (s) s.textContent = data.status;
        const st = document.getElementById('ai-started');
        if (st) st.textContent = data.started || '-';
        const lr = document.getElementById('ai-last-reply');
        if (lr) lr.textContent = data.last_reply || '-';
    }).catch(function(){});
}
function pollPool() {
    fetch('/api/pool').then(function(res){ return res.json(); }).then(function(data){
        const k = document.getElementById('pool-key');
        if (k) k.textContent = data.active_key;
        const c = document.getElementById('pool-calls');
        if (c) c.textContent = data.recent_calls;
        const f = document.getElementById('pool-failover');
        if (f) f.textContent = data.last_failover || 'none';
    }).catch(function(){});
}
document.addEventListener('DOMContentLoaded', function() {
    initAdsbMap();
    pollAircraft();
    pollRecent();
    pollAiStatus();
    pollPool();
    setInterval(pollAircraft, 30000);
    setInterval(pollRecent, 10000);
    setInterval(pollAiStatus, 10000);
    setInterval(pollPool, 15000);
});
"""

# ---------------- ADS-B poller Python code (before HTML_PAGE) ----------------
POLLER_CODE = """# --- LIVE ADS-B MAP FEED ---
# Background poller: fetches the same opendata.adsb.fi feed the voice hub uses
# (75 NM around Shawnee) once a minute and keeps the latest aircraft list in
# memory for the /api/aircraft endpoint. Priority fleets match the voice hub.
ADSB_URL = "https://opendata.adsb.fi/api/v3/lat/38.9900/lon/-94.7600/dist/75"
ADSB_CENTER_LAT = 38.9900
ADSB_CENTER_LON = -94.7600
KCMO_POLICE_FLEET = ["N690PD", "N691PD", "N692PD"]
KANSAS_HIGHWAY_PATROL = ["N650HP", "N670HP", "N600HP", "N900HP", "N940HP", "N950HP"]
MISSOURI_HIGHWAY_PATROL = ["N93MP", "N95MP", "N79MP", "N83MP", "N86MP", "N94MP"]
_aircraft_cache = {"updated": 0, "aircraft": []}

def _adsb_priority(reg):
    reg = (reg or "").strip().upper()
    if reg in KCMO_POLICE_FLEET:
        return "pd"
    if reg in KANSAS_HIGHWAY_PATROL:
        return "khp"
    if reg in MISSOURI_HIGHWAY_PATROL:
        return "mshp"
    return ""

def _adsb_poll_once():
    req = urllib.request.Request(ADSB_URL, headers={"User-Agent": "KF0RIZ-hub-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    out = []
    for a in data.get("ac", []):
        lat = a.get("lat")
        lon = a.get("lon")
        if lat is None or lon is None:
            continue
        reg = (a.get("r") or "").strip().upper()
        callsign = (a.get("flight") or "").strip() or reg or (a.get("hex") or "")
        alt = a.get("alt_baro")
        if alt is None:
            alt = a.get("alt_geom")
        out.append({
            "callsign": callsign,
            "reg": reg,
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "spd": a.get("gs"),
            "track": a.get("track"),
            "type": (a.get("t") or "") or (a.get("desc") or ""),
            "dst": a.get("dst"),
            "priority": _adsb_priority(reg),
        })
    _aircraft_cache["updated"] = int(time.time())
    _aircraft_cache["aircraft"] = out

def _adsb_poller():
    while True:
        try:
            _adsb_poll_once()
        except Exception:
            pass
        time.sleep(60)

threading.Thread(target=_adsb_poller, daemon=True).start()

"""

# ---------------- new Flask routes (before /stream) ----------------
ROUTES_CODE = '''def _tail_log(n=300):
    try:
        res = subprocess.run(['tail', '-n', str(n), '/var/log/ai_orchestrator.log'], capture_output=True, text=True, errors='replace', timeout=5)
        return res.stdout.splitlines()
    except Exception:
        return []

def _log_time(line):
    m = re.search(r'\\[(\\d{2}:\\d{2}:\\d{2})', line)
    return m.group(1) if m else ""

@app.route('/api/aircraft')
def aircraft_api():
    ac = list(_aircraft_cache["aircraft"])
    nearest = None
    for a in ac:
        if a.get("dst") is None:
            continue
        if nearest is None or a["dst"] < nearest["dst"]:
            nearest = a
    pri = sum(1 for a in ac if a.get("priority"))
    updated_str = ""
    if _aircraft_cache["updated"]:
        updated_str = time.strftime("%H:%M:%S", time.localtime(_aircraft_cache["updated"]))
    return jsonify({
        "count": len(ac),
        "nearest": nearest,
        "priority_count": pri,
        "updated": _aircraft_cache["updated"],
        "updated_str": updated_str,
        "aircraft": ac,
    })

@app.route('/api/recent')
def recent_api():
    items = []
    pending_q = None
    pending_t = ""
    for line in _tail_log(300):
        if "[RADIO INTERPRETATION]" in line and "Heard:" in line:
            pending_q = line.split("Heard:", 1)[1].strip().strip('"').strip()
            pending_t = _log_time(line)
        elif "[GEMINI RESPONSE]" in line and "Saying:" in line and pending_q:
            ans = line.split("Saying:", 1)[1].strip().strip('"').strip()
            items.append({"time": pending_t, "q": pending_q, "a": ans})
            pending_q = None
    return jsonify({"items": items[-5:]})

@app.route('/api/ai_status')
def ai_status_api():
    status = "unknown"
    started = ""
    try:
        r = subprocess.run(['systemctl', 'is-active', 'ai_orchestrator.service'], capture_output=True, text=True, errors='replace', timeout=5)
        status = r.stdout.strip() or "unknown"
    except Exception:
        pass
    try:
        r = subprocess.run(['systemctl', 'show', 'ai_orchestrator.service', '--property=ActiveEnterTimestamp'], capture_output=True, text=True, errors='replace', timeout=5)
        started = r.stdout.strip().split("=", 1)[1].strip() if "=" in r.stdout else ""
    except Exception:
        pass
    last_reply = ""
    for line in reversed(_tail_log(300)):
        if "[GEMINI RESPONSE]" in line:
            last_reply = _log_time(line)
            break
    return jsonify({"status": status, "started": started, "last_reply": last_reply})

@app.route('/api/pool')
def pool_api():
    active_key = "-"
    recent_calls = 0
    last_failover = ""
    for line in _tail_log(300):
        if "[GEMINI RESPONSE]" in line:
            recent_calls += 1
        m = re.search(r'Key Pool Index \\[(\\d+)\\]', line)
        if m:
            active_key = m.group(1)
        m = re.search(r'Key (\\d+) submitted', line)
        if m:
            active_key = m.group(1)
        low = line.lower()
        if "failover" in low or "pool exhaustion" in low:
            last_failover = _log_time(line) or "recent"
    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover})

'''

# ---------------- edits ----------------
# ORDER MATTERS: the JS insert (before </script>) must run BEFORE the Leaflet
# insert (before </head>), because the Leaflet <script> tag itself contains a
# </script> that would make the JS anchor match twice.
EDITS = [
    ("imports (threading/json/urllib)",
     "import re\nfrom flask import Flask, Response, render_template_string, jsonify, request",
     "import re\nimport threading\nimport json\nimport urllib.request\nfrom flask import Flask, Response, render_template_string, jsonify, request"),
    ("body min-height so page scrolls with new panels",
     "display: flex; flex-direction: column; height: 100vh;",
     "display: flex; flex-direction: column; min-height: 100vh;"),
    ("terminal fixed height",
     "#terminal { flex-grow: 1;",
     "#terminal { height: 320px; flex-shrink: 0;"),
    ("new panel CSS",
     "</style>",
     NEW_CSS + "</style>"),
    ("new map/status/QA JS",
     "</script>",
     NEW_JS + "</script>"),
    ("Leaflet CDN",
     "</head>",
     LEAFLET_CDN + "</head>"),
    ("new panels HTML + log filter + terminal",
     "<div id=\"terminal\"></div>",
     NEW_PANELS.strip()),
    ("AMI log filter in stream handler",
     "    if (event.data.trim() === \"\") return;",
     "    if (event.data.trim() === \"\") return;\n    var _ha = document.getElementById('hide-ami');\n    if (_ha && _ha.checked && event.data.indexOf('[AMI EVENT]') !== -1) return;"),
    ("ADS-B poller code",
     "HTML_PAGE = \"\"\"",
     POLLER_CODE + "HTML_PAGE = \"\"\""),
    ("new API routes",
     "@app.route('/stream')",
     ROUTES_CODE + "@app.route('/stream')"),
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
