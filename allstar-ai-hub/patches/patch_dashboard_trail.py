#!/usr/bin/env python3
"""Dashboard: fix the black zoom + click a plane to see its flight path.
Zoom fix:
- The Leaflet CSS link was missing a slash (leaflet@1.9.4dist/...) so the
  stylesheet 404'd; that breaks tile rendering at high zoom. Fixed to
  leaflet@1.9.4/dist/leaflet.css.
- Tile layer now sets maxNativeZoom 19 so Leaflet never asks for tiles
  beyond what OpenStreetMap serves.
Flight path (like FlightRadar):
- The dashboard now remembers each plane's recent positions (last 30
  fixes, up to 15 min) as it polls.
- Tap/click a plane on the map and it draws its trail behind it (blue
  line) plus a projected path ahead (green dashed line, from its current
  heading + ground speed), and opens a popup with callsign / type /
  altitude / speed.
Target: /home/asl/ai_dashboard.py with the fullscreen patch applied.
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import math
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_trail_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("Fix Leaflet CSS URL (missing slash -> 404)",
     "https://unpkg.com/leaflet@1.9.4dist/leaflet.css",
     "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"),
    ("Tile layer maxNativeZoom 19",
     "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution:",
     "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, maxNativeZoom: 19, attribution:"),
    ("Import math for the trail projection",
     "import json",
     "import json\nimport math"),
    ("Trail store dict",
     "_aircraft_cache = []",
     "_aircraft_cache = []\n_trail = {}"),
    ("Record positions into the trail on each poll",
     '        _aircraft_cache = data.get("ac", [])',
     '        _aircraft_cache = data.get("ac", [])\n        _now = time.time()\n        for _a in _aircraft_cache:\n            _hx = _a.get("hex")\n            _la = _a.get("lat"); _lo = _a.get("lon")\n            if not _hx or _la is None or _lo is None:\n                continue\n            _lst = _trail.setdefault(_hx, [])\n            _lst.append([_la, _lo, _now])\n            _trail[_hx] = [p for p in _lst if _now - p[2] <= 900][-30:]'),
    ("Trail API route before /stream",
     "@app.route('/stream')",
     "@app.route('/api/trail/<hx>')\ndef api_trail(hx):\n    _now = time.time()\n    _pts = [[p[0], p[1]] for p in _trail.get(hx, []) if _now - p[2] <= 900]\n    _fwd = []\n    _ac = None\n    for _a in _aircraft_cache:\n        if _a.get('hex') == hx:\n            _ac = _a; break\n    if _ac is not None and _ac.get('lat') is not None and _ac.get('lon') is not None:\n        _trk = _ac.get('track'); _gs = _ac.get('gs')\n        if _trk is not None and _gs:\n            _la0 = float(_ac['lat']); _lo0 = float(_ac['lon'])\n            _rad = math.radians(float(_trk))\n            for _mins in (2, 5, 10):\n                _dist = float(_gs) * (_mins / 60.0)\n                _dla = _dist * math.cos(_rad) / 60.0\n                _dlo = _dist * math.sin(_rad) / (60.0 * max(0.2, math.cos(math.radians(_la0))))\n                _fwd.append([_la0 + _dla, _lo0 + _dlo])\n    return jsonify({'hex': hx, 'trail': _pts, 'forward': _fwd, 'aircraft': _ac})\n\n@app.route('/stream')"),
    ("JS: click a plane to show its trail + forward path",
     "                    adsbMarkers[key] = m;",
     "                    adsbMarkers[key] = m;\n                    (function(mk, ac){ mk.on('click', function(){\n                        var hx = ac.hex || ac.reg || ac.callsign;\n                        if (!hx) return;\n                        fetch('/api/trail/' + encodeURIComponent(hx)).then(function(r){ return r.json(); }).then(function(d){\n                            if (adsbMap._trailLine) { adsbMap.removeLayer(adsbMap._trailLine); adsbMap._trailLine = null; }\n                            if (adsbMap._fwdLine) { adsbMap.removeLayer(adsbMap._fwdLine); adsbMap._fwdLine = null; }\n                            if (d.trail && d.trail.length > 1) { adsbMap._trailLine = L.polyline(d.trail, {color: '#58a6ff', weight: 3}).addTo(adsbMap); }\n                            if (d.forward && d.forward.length > 0) { var fp = [[ac.lat, ac.lon]].concat(d.forward); adsbMap._fwdLine = L.polyline(fp, {color: '#3fb950', weight: 3, dashArray: '6 6'}).addTo(adsbMap); }\n                            var info = (ac.callsign || ac.reg || hx) + (ac.type ? ' (' + ac.type + ')' : '') + '<br>Alt ' + (ac.alt ? ac.alt.toLocaleString() + ' ft' : '-') + ' &nbsp; Spd ' + (ac.spd ? ac.spd + ' kt' : '-');\n                            L.popup().setLatLng([ac.lat, ac.lon]).setContent(info).openOn(adsbMap);\n                        });\n                    }); })(m, a);"),
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
