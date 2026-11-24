#!/usr/bin/env python3
"""Add a SOLAR / PROPAGATION panel to the AI hub dashboard (ai_dashboard.py).

v2 (patch_dashboard_solar_b.py): anchors corrected to the LIVE file (Nov 24 11:29-11:32).
The v1 patch aborted on edit 4 because the staged copy it was built from had
deeper indentation than the live file. All anchors below were verified against
the live /home/asl/ai_dashboard.py (qa-list lines 319-322, pool-failover lines
674-678, pollHealth lines 688-689).

v3 (patch_dashboard_solar_c.py): edit 5a anchor replaced. v2 aborted on edit 5
because live line 674 carries FIVE leading spaces (inconsistent indent in the
live file), not the four the anchor assumed. The new edit-5a anchor is the
2-line boundary between the end of pollPool (} at col 0) and the
DOMContentLoaded listener (col 0) — it avoids the pool-failover lines entirely.
Verified present exactly once in the live region (Nov 24 11:59).

What it adds:
  - /api/solar route: fetches the free N0NBH feed (https://www.hamqsl.com/solarxml.php),
    parses it with stdlib ElementTree, caches server-side 30 min (feed updates
    ~hourly; N0NBH asks max every 30-60 min). Fail-open: on fetch error it
    serves the last good cached data, else {"error": ...} and the panel shows
    "unavailable" instead of breaking the dashboard. No new packages/keys.
  - HTML panel at the bottom (after RECENT Q&A, before the log terminal):
    SFI/SN/A/K/X-ray/304A, solar wind/Bz/aurora/geomag/noise/MUF, HF band
    ratings day/night color-coded (Good green / Fair yellow / Poor red),
    VHF phenomena, plus the NASA SDO 304A sun image (512px hotlink) and a
    "Data: N0NBH / hamqsl.com - Sun image: NASA/SDO" credit line.
  - JS pollSolar() wired into DOMContentLoaded + 30-min interval.

Backups: the script refuses to run unless it can write a backup copy first.
Rollback: cp <backup> /home/asl/ai_dashboard.py && sudo systemctl restart ai_dashboard
Run on the hub as: sudo python3 patch_dashboard_solar_b.py
"""
import os
import shutil
import sys

TARGET = '/home/asl/ai_dashboard.py'
BACKUP_DIR = '/home/asl/backups/20261124'
BACKUP = os.path.join(BACKUP_DIR, 'ai_dashboard.py.solar')

EDITS = [
    # 1. ElementTree import (stdlib XML parser for the N0NBH feed)
    (
        "import urllib.request\nfrom flask import Flask, Response, render_template_string, jsonify, request",
        "import urllib.request\nimport xml.etree.ElementTree as ET\nfrom flask import Flask, Response, render_template_string, jsonify, request",
    ),
    # 2. Solar cache dict next to the other caches
    (
        "_route_cache = {}\n_aviation_cache = {}",
        "_route_cache = {}\n_solar_cache = {}\n_aviation_cache = {}",
    ),
    # 3. /api/solar route, right after the /api/health route
    (
        "    return jsonify({'temp_c': temp_c, 'load1': load1, 'uptime_s': up_s, 'disk_free_gb': disk_free_gb})\n\n@app.route('/api/trail/<hx>')",
        "    return jsonify({'temp_c': temp_c, 'load1': load1, 'uptime_s': up_s, 'disk_free_gb': disk_free_gb})\n\n# --- SOLAR / PROPAGATION (free N0NBH feed, hamqsl.com/solarxml.php) ---\n# Feed updates ~hourly; N0NBH asks it be read at most every 30-60 min.\n# Cache 30 min server-side; fail open (serve last good data on fetch error).\nSOLAR_URL = 'https://www.hamqsl.com/solarxml.php'\nSOLAR_CACHE_TTL = 1800\nNOAA_FORECAST_URL = 'https://services.swpc.noaa.gov/text/3-day-forecast.txt'\nNOAA_CACHE_TTL = 21600\n_noaa_cache = {}\ndef _noaa_flare_r1r2():\n    now = int(time.time())\n    ent = _noaa_cache.get('data')\n    if ent and now - ent[0] < NOAA_CACHE_TTL:\n        return ent[1]\n    try:\n        req = urllib.request.Request(NOAA_FORECAST_URL, headers={'User-Agent': 'KFORIZ-hub-dashboard/1.0'})\n        with urllib.request.urlopen(req, timeout=10) as resp:\n            txt = resp.read().decode('utf-8', 'replace')\n        m = re.search(r'^R1-R2\\s+(\\d+)%', txt, re.M)\n        val = m.group(1) if m else None\n        _noaa_cache['data'] = (now, val)\n        return val\n    except Exception:\n        return ent[1] if ent else None\n_VHF_LABELS = {\n    ('vhf-aurora', 'northern_hemi'): 'Aurora',\n    ('E-Skip', 'europe_6m'): '6m EsEU',\n    ('E-Skip', 'europe_4m'): '4m EsEU',\n    ('E-Skip', 'europe'): '2m EsEU',\n    ('E-Skip', 'north_america'): '2m EsNA',\n}\ndef _solar_text(el, tag):\n    n = el.find(tag)\n    if n is None or n.text is None:\n        return None\n    return n.text.strip() or None\n@app.route('/api/solar')\ndef solar_api():\n    now = int(time.time())\n    ent = _solar_cache.get('data')\n    if ent and now - ent[0] < SOLAR_CACHE_TTL:\n        return jsonify(ent[1])\n    try:\n        req = urllib.request.Request(SOLAR_URL, headers={'User-Agent': 'KFORIZ-hub-dashboard/1.0'})\n        with urllib.request.urlopen(req, timeout=10) as resp:\n            raw = resp.read()\n        root = ET.fromstring(raw)\n        sd = root.find('solardata')\n        if sd is None:\n            raise ValueError('no solardata')\n        hf = {}\n        cc = sd.find('calculatedconditions')\n        if cc is not None:\n            for b in cc.findall('band'):\n                name = (b.get('name') or '').strip()\n                tm = (b.get('time') or '').strip()\n                val = (b.text or '').strip()\n                if name and tm and val:\n                    hf.setdefault(name, {})[tm] = val\n        vhf = []\n        vc = sd.find('calculatedvhfconditions')\n        if vc is not None:\n            for p in vc.findall('phenomenon'):\n                name = (p.get('name') or '').strip()\n                loc = (p.get('location') or '').strip()\n                val = (p.text or '').strip()\n                label = _VHF_LABELS.get((name, loc)) or (name + ' ' + loc).strip()\n                vhf.append({'label': label, 'value': val})\n        out = {\n            'updated': _solar_text(sd, 'updated'),\n            'solarflux': _solar_text(sd, 'solarflux'),\n            'sunspots': _solar_text(sd, 'sunspots'),\n            'aindex': _solar_text(sd, 'aindex'),\n            'kindex': _solar_text(sd, 'kindex'),\n            'xray': _solar_text(sd, 'xray'),\n            'heliumline': _solar_text(sd, 'heliumline'),\n            'protonflux': _solar_text(sd, 'protonflux'),\n            'electonflux': _solar_text(sd, 'electonflux'),\n            'aurora': _solar_text(sd, 'aurora'),\n            'latdegree': _solar_text(sd, 'latdegree'),\n            'solarwind': _solar_text(sd, 'solarwind'),\n            'magneticfield': _solar_text(sd, 'magneticfield'),\n            'geomagfield': _solar_text(sd, 'geomagfield'),\n            'signalnoise': _solar_text(sd, 'signalnoise'),\n            'muf': _solar_text(sd, 'muf'),\n            'flare_r1r2': _noaa_flare_r1r2(),\n            'hf': hf,\n            'vhf': vhf,\n        }\n        _solar_cache['data'] = (now, out)\n        return jsonify(out)\n    except Exception:\n        if ent:\n            return jsonify(ent[1])\n        return jsonify({'error': 'solar data unavailable'})\n\n@app.route('/api/trail/<hx>')",
    ),
    # 4. HTML panel after RECENT Q&A, before the log filter/terminal.
    # LIVE anchor (lines 319-322): qa-list at 4 spaces, panel close at col 0,
    # filter-row at col 0 with the full label on one line.
    (
        "    <div id=\"qa-list\"><div class=\"qa-empty\">Loading...</div></div>\n</div>\n\n<div class=\"filter-row\"><label><input type=\"checkbox\" id=\"hide-ami\" checked> Hide AMI events in log</label></div>",
        "    <div id=\"qa-list\"><div class=\"qa-empty\">Loading...</div></div>\n</div>\n\n<div class=\"panel\">\n    <div class=\"panel-title\">SOLAR / PROPAGATION</div>\n    <div class=\"stat-line\" id=\"solar-top\">Loading solar data...</div>\n    <div class=\"stat-line\" id=\"solar-mid\"></div>\n    <div class=\"stat-line\" id=\"solar-hf\"></div>\n    <div class=\"stat-line\" id=\"solar-vhf\"></div>\n    <div style=\"margin-top:6px;\"><img id=\"solar-img\" src=\"https://sdo.gsfc.nasa.gov/assets/img/latest/latest_512_0304.jpg\" alt=\"SDO 304A sun\" style=\"max-width:170px;border-radius:6px;\"></div>\n    <div class=\"adsb-updated\" id=\"solar-credit\">Solar data: N0NBH / hamqsl.com &middot; Sun image: NASA/SDO</div>\n</div>\n\n<div class=\"filter-row\"><label><input type=\"checkbox\" id=\"hide-ami\" checked> Hide AMI events in log</label></div>",
    ),
    # 5a. pollSolar() + colorBand() after pollPool().
    # Anchor is the 2-line boundary between the end of pollPool (line 677, } at
    # col 0) and the DOMContentLoaded listener (line 678, col 0). The other
    # DOMContentLoaded (line 347) is indented 8 spaces, so this col-0 pair is
    # unique. Deliberately avoids the pool-failover lines: live line 674 has
    # FIVE leading spaces (inconsistent indent), which broke the v2 anchor.
    (
        "}\ndocument.addEventListener('DOMContentLoaded', function() {",
        "}\nfunction colorBand(v) {\n    var c = '#f85149';\n    if (v === 'Good') c = '#3fb950';\n    else if (v === 'Fair') c = '#e3b341';\n    return '<span style=\"color:' + c + ';\">' + v + '</span>';\n}\nfunction pollSolar() {\n    fetch('/api/solar').then(function(r){ return r.json(); }).then(function(d){\n        var top = document.getElementById('solar-top');\n        if (!top) return;\n        if (d.error) { top.textContent = 'Solar data unavailable'; return; }\n        var dash = function(v){ return (v === null || v === undefined || v === '') ? '-' : v; };\n        top.textContent = 'SFI ' + dash(d.solarflux) + ' | SN ' + dash(d.sunspots) + ' | A ' + dash(d.aindex) + ' | K ' + dash(d.kindex) + ' | X-ray ' + dash(d.xray) + ' | 304A ' + dash(d.heliumline) + ' | Flare ' + ((d.flare_r1r2 !== null && d.flare_r1r2 !== undefined) ? d.flare_r1r2 + '%' : '-') + ' (NOAA)';\n        var mid = document.getElementById('solar-mid');\n        if (mid) mid.textContent = 'Wind ' + dash(d.solarwind) + ' km/s | Bz ' + dash(d.magneticfield) + ' | Aurora ' + dash(d.aurora) + ' (' + dash(d.latdegree) + ' deg) | Geomag ' + dash(d.geomagfield) + ' | Noise ' + dash(d.signalnoise) + ' | MUF ' + dash(d.muf);\n        var hf = document.getElementById('solar-hf');\n        if (hf && d.hf) {\n            hf.innerHTML = 'HF Day/Night: ' + Object.keys(d.hf).map(function(b){\n                return b + ' ' + colorBand(d.hf[b].day || '-') + '/' + colorBand(d.hf[b].night || '-');\n            }).join(' &middot; ');\n        }\n        var vhf = document.getElementById('solar-vhf');\n        if (vhf && d.vhf) {\n            vhf.textContent = 'VHF: ' + d.vhf.map(function(p){ return p.label + ' ' + p.value; }).join(' &middot; ');\n        }\n        var cr = document.getElementById('solar-credit');\n        if (cr) cr.innerHTML = 'Updated ' + dash(d.updated) + ' &middot; Solar data: N0NBH / hamqsl.com &middot; Flare: NOAA SWPC &middot; Sun image: NASA/SDO';\n    }).catch(function(){});\n}\ndocument.addEventListener('DOMContentLoaded', function() {",
    ),
    # 5b. Wire pollSolar into DOMContentLoaded + 30-min interval.
    # LIVE anchor (lines 688-689): 4-space indent.
    (
        "    pollHealth();\n    setInterval(pollHealth, 30000);",
        "    pollHealth();\n    setInterval(pollHealth, 30000);\n    pollSolar();\n    setInterval(pollSolar, 1800000);",
    ),
]

def main():
    if not os.path.exists(TARGET):
        print('PATCH ABORTED: target %s not found' % TARGET)
        return 1
    with open(TARGET, 'r') as f:
        src = f.read()
    for i, (old, new) in enumerate(EDITS, 1):
        if old not in src:
            print('PATCH ABORTED: edit %d anchor not found' % i)
            return 1
        if src.count(old) != 1:
            print('PATCH ABORTED: edit %d anchor not unique (%d matches)' % (i, src.count(old)))
            return 1
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(TARGET, BACKUP)
    print('backup saved: %s' % BACKUP)
    for i, (old, new) in enumerate(EDITS, 1):
        src = src.replace(old, new, 1)
        print('edit %d ok' % i)
    with open(TARGET, 'w') as f:
        f.write(src)
    print('PATCH OK (%d edits)' % len(EDITS))
    return 0

if __name__ == '__main__':
    sys.exit(main())
