#!/usr/bin/env python3
"""Dashboard v2: fix the black zoom + click a plane for trail + route.
Black zoom (confirmed by Sam's grep, line 382): the MAP allows zoom 19
but the TILE LAYER was capped at maxZoom 12, so past zoom 12 there are
no tiles and the map goes black. Fix: tile layer maxZoom 12 -> 19 and
add maxNativeZoom 19. (The Leaflet CSS link is FINE - line 186 is the
correct URL; an earlier patch wrongly assumed a typo from a cut-off
grep line and aborted.)
Flight path: tap a plane -> blue trail behind it (last 30 fixes, 15 min)
+ green dashed projection ahead (heading + speed) + popup.
Route: tap a plane also asks OpenSky Network (free) for that aircraft's
most recent completed flight and shows origin -> destination. OpenSky
only knows a route once the flight has landed, so this is the LAST
completed flight's route (usually the same trip for airliners), labelled
as such. If OpenSky is unreachable or has no flight, the popup just
omits the route line - nothing else breaks. Result cached 10 min per
aircraft; only fetched on tap, never in the background poll.
Target: /home/asl/ai_dashboard.py.
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
TMP = "/tmp/ai_dashboard_trail2_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("Tile layer maxZoom 12 -> 19 + maxNativeZoom (black zoom fix)",
     "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 12, attribution:",
     "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, maxNativeZoom: 19, attribution:"),
    ("Import math for the trail projection",
     "import json",
     "import json\nimport math"),
    ("Trail + route-cache stores",
     "_aircraft_cache = []",
     "_aircraft_cache = []\n_trail = {}\n_route_cache = {}"),
    ("Record positions into the trail on each poll",
     '        _aircraft_cache = data.get("ac", [])',
     '        _aircraft_cache = data.get("ac", [])\n        _now = time.time()\n        for _a in _aircraft_cache:\n            _hx = _a.get("hex")\n            _la = _a.get("lat"); _lo = _a.get("lon")\n            if not _hx or _la is None or _lo is None:\n                continue\n            _lst = _trail.setdefault(_hx, [])\n            _lst.append([_la, _lo, _now])\n            _trail[_hx] = [p for p in _lst if _now - p[2] <= 900][-30:]'),
    ("Trail + route API routes before /stream",
     "@app.route('/stream')",
     "@app.route('/api/trail/<hx>')\ndef api_trail(hx):\n    _now = time.time()\n    _pts = [[p[0], p[1]] for p in _trail.get(hx, []) if _now - p[2] <= 900]\n    _fwd = []\n    _ac = None\n    for _a in _aircraft_cache:\n        if _a.get('hex') == hx:\n            _ac = _a; break\n    if _ac is not None and _ac.get('lat') is not None and _ac.get('lon') is not None:\n        _trk = _ac.get('track'); _gs = _ac.get('gs')\n        if _trk is not None and _gs:\n            _la0 = float(_ac['lat']); _lo0 = float(_ac['lon'])\n            _rad = math.radians(float(_trk))\n            for _mins in (2, 5, 10):\n                _dist = float(_gs) * (_mins / 60.0)\n                _dla = _dist * math.cos(_rad) / 60.0\n                _dlo = _dist * math.sin(_rad) / (60.0 * max(0.2, math.cos(math.radians(_la0))))\n                _fwd.append([_la0 + _dla, _lo0 + _dlo])\n    return jsonify({'hex': hx, 'trail': _pts, 'forward': _fwd, 'aircraft': _ac})\n\n@app.route('/api/route/<hx>')\ndef api_route(hx):\n    hx = hx.lower()\n    now = int(time.time())\n    ent = _route_cache.get(hx)\n    if ent and now - ent[0] < 600:\n        return jsonify(ent[1])\n    origin = None; dest = None\n    try:\n        begin = now - 86400\n        url = 'https://opensky-network.org/api/flights/aircraft?icao24=%s&begin=%d&end=%d' % (hx, begin, now)\n        req = urllib.request.Request(url, headers={'User-Agent': 'KF0RIZ-hub-dashboard/1.0'})\n        with urllib.request.urlopen(req, timeout=8) as resp:\n            flights = json.load(resp)\n        if flights:\n            f = max(flights, key=lambda x: x.get('lastSeen') or 0)\n            origin = f.get('estDepartureAirport')\n            dest = f.get('estArrivalAirport')\n    except Exception:\n        pass\n    out = {'hex': hx, 'origin': origin, 'destination': dest}\n    _route_cache[hx] = (now, out)\n    return jsonify(out)\n\n@app.route('/stream')"),
    ("JS: click a plane -> trail + forward path + route in popup",
     "                    adsbMarkers[key] = m;",
     "                    adsbMarkers[key] = m;\n                    (function(mk, ac){ mk.on('click', function(){\n                        var hx = ac.hex || ac.reg || ac.callsign;\n                        if (!hx) return;\n                        var trailP = fetch('/api/trail/' + encodeURIComponent(hx)).then(function(r){ return r.json(); });\n                        var routeP = fetch('/api/route/' + encodeURIComponent(hx)).then(function(r){ return r.json(); }).catch(function(){ return {}; });\n                        Promise.all([trailP, routeP]).then(function(res){\n                            var d = res[0], rt = res[1] || {};\n                            if (adsbMap._trailLine) { adsbMap.removeLayer(adsbMap._trailLine); adsbMap._trailLine = null; }\n                            if (adsbMap._fwdLine) { adsbMap.removeLayer(adsbMap._fwdLine); adsbMap._fwdLine = null; }\n                            if (d.trail && d.trail.length > 1) { adsbMap._trailLine = L.polyline(d.trail, {color: '#58a6ff', weight: 3}).addTo(adsbMap); }\n                            if (d.forward && d.forward.length > 0) { var fp = [[ac.lat, ac.lon]].concat(d.forward); adsbMap._fwdLine = L.polyline(fp, {color: '#3fb950', weight: 3, dashArray: '6 6'}).addTo(adsbMap); }\n                            var info = (ac.callsign || ac.reg || hx) + (ac.type ? ' (' + ac.type + ')' : '') + '<br>Alt ' + (ac.alt ? ac.alt.toLocaleString() + ' ft' : '-') + ' &nbsp; Spd ' + (ac.spd ? ac.spd + ' kt' : '-');\n                            if (rt.origin && rt.destination) { info += '<br>Route (last flight): ' + rt.origin + ' &rarr; ' + rt.destination; }\n                            L.popup().setLatLng([ac.lat, ac.lon]).setContent(info).openOn(adsbMap);\n                        });\n                    }); })(m, a);"),
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
