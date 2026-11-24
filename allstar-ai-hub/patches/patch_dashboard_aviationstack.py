#!/usr/bin/env python3
"""Dashboard: live flight route (origin -> destination) via AviationStack free tier.

- /api/route/<hex> now tries AviationStack FIRST (by the plane's callsign, from
  the aircraft cache), falling back to the OpenSky "last flight" lookup as before.
- AviationStack free plan: 100 lookups/month, no credit card. Key is read from
  /home/asl/.aviationstack_key (Sam creates it; the key is NEVER in this patch,
  the dashboard code, or git). If the file is missing/empty, the feature is
  silently disabled and only OpenSky is used.
- Results are cached per callsign (6h for a hit, 1h for a miss) so tapping the
  same flight does not burn quota. Only airline-style callsigns (3 letters +
  digits) are looked up; N-numbers, helicopters and GA are skipped.
- Popup shows "Route: ORIGIN -> DEST" for a live AviationStack route, and
  "Route (last flight): ..." for the OpenSky fallback, as before.
- Requires backup /home/asl/backups/20261123/ai_dashboard.py to exist.
- Writes via temp file + py_compile + shutil.copyfile; aborts safely if any
  anchor is not found exactly once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_aviationstack.py"

if not os.path.isfile(BACKUP):
    print("PATCH ABORTED: backup %s not found; refusing to edit live file" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

edits = []

# 1. AviationStack helper + cache, after the trail/route stores.
edits.append((
    "AviationStack helper + cache (after _route_cache)",
    '_aircraft_cache = {"updated": 0, "aircraft": []}\n_trail = {}\n_route_cache = {}',
    '_aircraft_cache = {"updated": 0, "aircraft": []}\n_trail = {}\n_route_cache = {}\n_aviation_cache = {}\n_aviation_key_val = None\n_aviation_key_val_next_try = 0\n\ndef _aviation_key():\n    global _aviation_key_val, _aviation_key_val_next_try\n    if _aviation_key_val:\n        return _aviation_key_val\n    _now = int(time.time())\n    if _now < _aviation_key_val_next_try:\n        return None\n    _aviation_key_val_next_try = _now + 60\n    try:\n        with open(\'/home/asl/.aviationstack_key\', \'r\', encoding=\'utf-8\') as _f:\n            _aviation_key_val = _f.read().strip() or None\n    except Exception:\n        _aviation_key_val = None\n    return _aviation_key_val\n\ndef _aviation_route(callsign):\n    _cs = (callsign or \'\').strip().upper()\n    if len(_cs) < 4 or len(_cs) > 8 or not _cs[:3].isalpha() or not any(c.isdigit() for c in _cs[3:]):\n        return (None, None)\n    _now = int(time.time())\n    _ent = _aviation_cache.get(_cs)\n    if _ent and _now - _ent[0] < (21600 if _ent[1][0] else 3600):\n        return _ent[1]\n    _out = (None, None)\n    _key = _aviation_key()\n    if _key:\n        try:\n            _url = \'https://api.aviationstack.com/v1/flights?access_key=%s&flight_icao=%s&limit=1\' % (_key, _cs)\n            _req = urllib.request.Request(_url, headers={\'User-Agent\': \'KF0RIZ-hub-dashboard/1.0\'})\n            with urllib.request.urlopen(_req, timeout=8) as _resp:\n                _data = json.load(_resp)\n            _flights = _data.get(\'data\') or []\n            if _flights:\n                _fl = _flights[0]\n                _dep = _fl.get(\'departure\') or {}\n                _arr = _fl.get(\'arrival\') or {}\n                _o = _dep.get(\'iata\') or _dep.get(\'icao\')\n                _d = _arr.get(\'iata\') or _arr.get(\'icao\')\n                if _o and _d:\n                    _out = (_o, _d)\n        except Exception:\n            _out = (None, None)\n    _aviation_cache[_cs] = (_now, _out)\n    return _out',
))

# 2. api_route: try AviationStack live route first, fall back to OpenSky.
_old_route = (
    "@app.route('/api/route/<hx>')\n"
    "def api_route(hx):\n"
    "    hx = hx.lower()\n"
    "    now = int(time.time())\n"
    "    ent = _route_cache.get(hx)\n"
    "    if ent and now - ent[0] < 600:\n"
    "        return jsonify(ent[1])\n"
    "    origin = None; dest = None\n"
    "    try:\n"
    "        begin = now - 86400\n"
    "        url = 'https://opensky-network.org/api/flights/aircraft?icao24=%s&begin=%d&end=%d' % (hx, begin, now)\n"
    "        req = urllib.request.Request(url, headers={'User-Agent': 'KF0RIZ-hub-dashboard/1.0'})\n"
    "        with urllib.request.urlopen(req, timeout=8) as resp:\n"
    "            flights = json.load(resp)\n"
    "        if flights:\n"
    "            f = max(flights, key=lambda x: x.get('lastSeen') or 0)\n"
    "            origin = f.get('estDepartureAirport')\n"
    "            dest = f.get('estArrivalAirport')\n"
    "    except Exception:\n"
    "        pass\n"
    "    out = {'hex': hx, 'origin': origin, 'destination': dest}\n"
    "    _route_cache[hx] = (now, out)\n"
    "    return jsonify(out)"
)
_new_route = (
    "@app.route('/api/route/<hx>')\n"
    "def api_route(hx):\n"
    "    hx = (hx or '').lower()\n"
    "    now = int(time.time())\n"
    "    ent = _route_cache.get(hx)\n"
    "    if ent and now - ent[0] < 600:\n"
    "        return jsonify(ent[1])\n"
    "    origin = None; dest = None; live = False\n"
    "    _cs = None\n"
    "    for _a in _aircraft_cache.get('aircraft') or []:\n"
    "        if (_a.get('hex') or '') == hx:\n"
    "            _cs = (_a.get('callsign') or '').strip()\n"
    "            break\n"
    "    if _cs:\n"
    "        _o, _d = _aviation_route(_cs)\n"
    "        if _o and _d:\n"
    "            origin, dest, live = _o, _d, True\n"
    "    if not (origin and dest):\n"
    "        try:\n"
    "            begin = now - 86400\n"
    "            url = 'https://opensky-network.org/api/flights/aircraft?icao24=%s&begin=%d&end=%d' % (hx, begin, now)\n"
    "            req = urllib.request.Request(url, headers={'User-Agent': 'KF0RIZ-hub-dashboard/1.0'})\n"
    "            with urllib.request.urlopen(req, timeout=8) as resp:\n"
    "                flights = json.load(resp)\n"
    "            if flights:\n"
    "                f = max(flights, key=lambda x: x.get('lastSeen') or 0)\n"
    "                origin = f.get('estDepartureAirport')\n"
    "                dest = f.get('estArrivalAirport')\n"
    "        except Exception:\n"
    "            pass\n"
    "    out = {'hex': hx, 'origin': origin, 'destination': dest, 'live': live}\n"
    "    _route_cache[hx] = (now, out)\n"
    "    return jsonify(out)"
)
edits.append((
    "api_route: AviationStack live first, OpenSky fallback",
    _old_route,
    _new_route,
))

# 3. JS popup: label a live route "Route:" and keep "(last flight)" for OpenSky.
edits.append((
    "JS popup: live route label",
    "if (rt.origin && rt.destination) { info += '<br>Route (last flight): ' + rt.origin + ' &rarr; ' + rt.destination; }",
    "if (rt.origin && rt.destination) { info += '<br>Route' + (rt.live ? '' : ' (last flight)') + ': ' + rt.origin + ' &rarr; ' + rt.destination; }",
))

for name, old, new in edits:
    n = src.count(old)
    if n != 1:
        print("PATCH ABORTED: %s: expected exactly 1 occurrence, found %d" % (name, n))
        sys.exit(1)
    src = src.replace(old, new, 1)
    print("ok: %s" % name)

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
print("Then create the key file (silent prompt, key never in chat/git):")
print("  read -s KEY; echo -n \"$KEY\" > /home/asl/.aviationstack_key; chmod 600 /home/asl/.aviationstack_key")
