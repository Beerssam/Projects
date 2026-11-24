import os
import time
import subprocess
import re
import threading
import json
import math
import urllib.request
from flask import Flask, Response, render_template_string, jsonify, request
app = Flask(__name__)
# --- SECURE CONTROL ACCESS KEY ---
DASHBOARD_PASSWORD = "__REDACTED__"
# --- LIVE ADS-B MAP FEED ---
# Background poller: fetches the same opendata.adsb.fi feed the voice hub uses
# (200 NM around Shawnee) once a minute and keeps the latest aircraft list in
# memory for the /api/aircraft endpoint. Priority fleets match the voice hub.
ADSB_URL = "https://opendata.adsb.fi/api/v3/lat/38.9900/lon/-94.7600/dist/200"
ADSB_CENTER_LAT = 38.9900
ADSB_CENTER_LON = -94.7600
KCMO_POLICE_FLEET = ["N690PD", "N691PD", "N692PD"]
KANSAS_HIGHWAY_PATROL = ["N650HP", "N670HP", "N600HP", "N900HP", "N940HP", "N950HP"]
MISSOURI_HIGHWAY_PATROL = ["N93MP", "N95MP", "N79MP", "N83MP", "N86MP", "N94MP"]
aircraft_cache = {"updated": 0, "aircraft": []}
_trail = {}
_route_cache = {}
_aviation_cache = {}
_aviation_key_val = None
_aviation_key_val_next_try = 0
def _aviation_key():
    global _aviation_key_val, _aviation_key_val_next_try
    if _aviation_key_val:
        return _aviation_key_val
    _now = int(time.time())
    if _now < _aviation_key_val_next_try:
        return None
    _aviation_key_val_next_try = _now + 60
    try:
        with open('/home/asl/.aviationstack_key', 'r', encoding='utf-8') as _f:
            _aviation_key_val = _f.read().strip() or None
    except Exception:
        _aviation_key_val = None
    return _aviation_key_val
def _aviation_route(callsign):
    _cs = (callsign or '').strip().upper()
    if len(_cs) < 4 or len(_cs) > 8 or not _cs[:3].isalpha() or not any(c.isdigit() for c in _cs[3:]):
        return (None, None)
    _now = int(time.time())
    _ent = _aviation_cache.get(_cs)
    if _ent and _now - _ent[0] < (21600 if _ent[1][0] else 3600):
        return _ent[1]
    _out = (None, None)
    _key = _aviation_key()
    if _key:
        try:
            url = 'https://api.aviationstack.com/v1/flights?access_key=%s&flight_icao=%s&limit=1' % (_key, _cs)
            _req = urllib.request.Request(_url, headers={'User-Agent': 'KFORIZ-hub-dashboard/1.0'})
            with urllib.request.urlopen(_req, timeout=8) as _resp:
                _data = json.load(_resp)
            _flights = _data.get('data') or []
            if _flights:
                _fl = _flights[0]
                _dep = _fl.get('departure') or {}
                _arr = _fl.get('arrival') or {}
                _o = _dep.get('iata') or _dep.get('icao')
                _d = _arr.get('iata') or _arr.get('icao')
                if _o and _d:
                    _out = (_o, _d)
        except Exception:
            _out = (None, None)
    _aviation_cache[_cs] = (_now, _out)
    return _out

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
    _req = urllib.request.Request(ADSB_URL, headers={"User-Agent": "KFORIZ-hub-dashboard/1.0"})
    with urllib.request.urlopen(_req, timeout=10) as resp:
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
            "hex": (a.get("hex") or "").strip().lower(),
            "reg": reg,
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "spd": a.get("gs"),
            "track": a.get("track"),
            "type": (a.get("t") or "") or (a.get("desc") or ""),
            "dst": a.get("dst"),
            "category": a.get("category"),
            "priority": _adsb_priority(reg),
        })
    _aircraft_cache["updated"] = int(time.time())
    _aircraft_cache["aircraft"] = out
    _now = time.time()
    for _a in out:
        _hx = _a.get("hex")
        _la = _a.get("lat"); _lo = _a.get("lon")
        if not _hx or _la is None or _lo is None:
            continue
        _lst = _trail.setdefault(_hx, [])
        _lst.append([_la, _lo, _now])
        _trail[_hx] = [p for p in _lst if _now - p[2] <= 1800][-30:]

def _adsb_poller():
    while True:
        try:
            _adsb_poll_once()
        except Exception:
            pass
        time.sleep(60)

threading.Thread(target=_adsb_poller, daemon=True).start()

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KFORIZ // AI Hub Live Telemetry</title>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: 'Courier New', Courier, monospace; margin: 0; padding: 20px; display: flex; flex-direction: column; min-height: 100vh; box-sizing: border-box; }
        header { flex-shrink: 0; background-color: #161b22; padding: 15px; border-radius: 6px; border: 1px solid #30363d; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        .brand-block { display: flex; flex-direction: column; gap: 4px; }
        h1 { margin: 0; font-size: 1.2rem; color: #58a6ff; letter-spacing: 1px; }

        /* Live Node Link Tracker Style */
        .node-matrix { color: #8b949e; font-size: 0.85rem; font-weight: bold; letter-spacing: 0.5px; }
        .node-active { color: #58a6ff; }

        .status { color: #7fe7c4; font-weight: bold; font-size: 0.9rem; }

        .control-panel { flex-shrink: 0; background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 6px; margin-bottom: 15px; display: flex; flex-direction: column; gap: 12px; position: relative; }

        .control-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; width: 100%; max-width: 600px; }

        button { color: #ffffff; border: 1px solid #f0f6fc1f; padding: 10px 14px; border-radius: 6px; cursor: pointer; font-weight: bold; font-family: sans-serif; font-size: 0.88rem; transition: background 0.15s, border-color 0.15s; width: 100%; box-sizing: border-box; display: flex; align-items: center; justify-content: center; gap: 6px; }

        /* --- ACCENT COLOR PALETTE --- */
        .btn-id { background-color: #1f6feb; } /* Blue */
        .btn-id:hover { background-color: #388bfd; border-color: #8b949e; }

        .btn-restart { background-color: #d29922; } /* Amber */
        .btn-restart:hover { background-color: #e3b341; border-color: #8b949e; }

        .btn-start { background-color: #238636; } /* Green */
        .btn-start:hover { background-color: #2ea043; border-color: #8b949e; }

        .btn-stop { background-color: #da3637; } /* Red */
        .btn-stop:hover { background-color: #f85149; border-color: #8b949e; }

        .btn-reboot { background-color: #8957e5; } /* Purple */
        .btn-reboot:hover { background-color: #a371f7; border-color: #8b949e; }

        .btn-shutdown { background-color: #484f58; } /* Muted Slate */
        .btn-shutdown:hover { background-color: #6e7681; border-color: #8b949e; }

        #terminal { height: 320px; flex-shrink: 0; background-color: #010409; border: 1px solid #30363d; border-radius: 6px; padding: 15px; overflow-y: auto; white-space: pre-wrap; font-size: 0.9rem; line-height: 1.5; box-shadow: inset 0 0 10px rgba(0,0,0,0.8); }
        .log-line { margin-bottom: 4px; border-bottom: 1px solid #161b22; padding-bottom: 2px; }
        #action-status { color: #e3b341; font-weight: bold; font-size: 0.9rem; min-height: 18px; }

        .lock-wall {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(22, 27, 34, 0.98); backdrop-filter: blur(5px);
            display: flex; justify-content: center; align-items: center;
            border-radius: 6px; gap: 14px; box-sizing: border-box; padding: 15px; z-index: 100;
        }
        .lock-title { color: #e3b341; font-weight: bold; font-family: sans-serif; font-size: 0.85rem; letter-spacing: 0.5px; }
        .lock-input { background-color: #010409; color: #c9d1d9; border: 1px solid #30363d; padding: 8px 12px; border-radius: 6px; font-family: monospace; font-size: 0.85rem; outline: none; max-width: 200px; }
        @media (max-width: 768px) {
            body { padding: 10px; }
            .control-row { max-width: 100%; }
            button { padding: 12px; font-size: 0.95rem; }
            .lock-wall { flex-direction: column; justify-content: center; text-align: center; gap: 10px; height: 100%; }
            .lock-input, .lock-wall button { width: 90%; max-width: 280px; padding: 11px; text-align: center; font-size: 1rem; }
        }
        /* --- DASHBOARD UPGRADE: MAP / STATUS / Q&A PANELS --- */
        .panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; margin-bottom: 15px; }
        .ap-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #58a6ff; border-radius: 3px; padding: 0 3px; font-size: 7px; font-weight: 700; white-space: nowrap; }
        .poi-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #d29922; border-radius: 3px; padding: 0 3px; font-size: 7px; font-weight: 700; white-space: nowrap; }
        .fire-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #f85149; border-radius: 3px; padding: 0 3px; font-size: 7px; font-weight: 700; white-space: nowrap; }
        .map-fullscreen { position: fixed !important; inset: 0 !important; width: 100vw !important; width: 100dvw !important; height: 100vh !important; height: 100dvh !important; z-index: 1000 !important; border-radius: 0 !important; margin: 0 !important; padding: 0 !important; border: none !important; touch-action: none !important; overscroll-behavior: none !important; }
        .map-fs-btn { position: absolute !important; right: 10px !important; bottom: 10px !important; z-index: 1001 !important; width: auto !important; min-width: 0 !important; display: flex !important; align-items: center !important; justify-content: center !important; background: rgba(13,17,23,0.55) !important; color: #e6edf3 !important; border: 1px solid rgba(230,237,243,0.35) !important; border-radius: 6px !important; padding: 6px 9px !important; font-size: 18px !important; line-height: 1 !important; font-weight: 700 !important; cursor: pointer !important; }
        .map-fs-exit { position: fixed !important; right: 10px !important; top: 10px !important; z-index: 1002 !important; width: auto !important; min-width: 0 !important; display: none !important; align-items: center !important; justify-content: center !important; background: rgba(13,17,23,0.55) !important; color: #e6edf3 !important; border: 1px solid rgba(230,237,243,0.35) !important; border-radius: 6px !important; padding: 6px 10px !important; font-size: 18px !important; line-height: 1 !important; font-weight: 700 !important; cursor: pointer !important; }
        .map-fs-exit.map-fs-show { display: flex !important; }
        .panel-title { color: #58a6ff; font-size: 0.95rem; letter-spacing: 0.5px; margin-bottom: 10px; font-family: sans-serif; }
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
        .adsb-marker { background: transparent; border: none; }
        @media (min-width: 769px) {
            body { max-width: 1100px; margin: 0 auto; }
            #map { height: 420px; }
            #terminal { height: 420px; }
            .stat-grid { grid-template-columns: 1fr 1fr; }
        }
        .ac-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        .ac-table th { color: #8b949e; text-align: left; padding: 4px 6px; border-bottom: 1px solid #30363d; font-family: sans-serif; font-size: 0.8rem; }
        .ac-table td { padding: 4px 6px; border-bottom: 1px solid #161b22; color: #c9d1d9; }
        .ac-table tr.ac-pri { color: #f85149; font-weight: bold; }
        .ac-table tr[data-lat] { cursor: pointer; }
        .ac-table tr[data-lat]:hover td { background: #21262d; }
        #aircraft-list { max-height: 260px; overflow-y: auto; }
    </style>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
    <header>
        <div class="brand-block">
            <h1>[KFORIZ] AllStar VoIP AI Orchestrator</h1>
            <div id="links-render" class="node-matrix">... CONNECTIONS: <span style="color: #e3b341;">POLLING ASTERISK...</span></div>
        </div>
        <div class="status">● LIVE TELEMETRY STREAMING</div>
    </header>

    <div class="panel">
        <div class="panel-title">AI SERVICE</div>
        <div class="stat-line">STATUS: <b id="ai-status">...</b></div>
        <div class="stat-line">STARTED: <b id="ai-started">...</b></div>
        <div class="stat-line">LAST REPLY: <b id="ai-last-reply">...</b></div>
        <div class="stat-line">LAST KEY-UP: <b id="ai-last-keyup">...</b></div>
    </div>

    <div class="panel">
        <div class="panel-title">HUB HEALTH</div>
        <div class="stat-line" id="hub-health">Loading...</div>
    </div>
    <div class="control-panel">
        <div id="lock-overlay" class="lock-wall">
            <span class="lock-title">🔒 SYSTEM CONSOLE LOCKED</span>
            <input type="password" id="pass-input" class="lock-input" placeholder="Enter Control Key...">
            <button onclick="unlockControls()" class="btn-start" style="width: auto;">Unlock</button>
        </div>

        <div class="control-row">
            <button onclick="triggerAction('id_node')" class="btn-id">🆔 ID Node</button>
            <button onclick="triggerAction('ai_restart')" class="btn-restart">🔄 Restart AI</button>
        </div>

        <div class="control-row">
            <button onclick="triggerAction('ai_start')" class="btn-start">▶ Start AI</button>
            <button onclick="triggerAction('ai_stop')" class="btn-stop">⏹ Stop AI</button>
        </div>

        <div class="control-row">
            <button onclick="confirmSystemAction('pi_reboot')" class="btn-reboot">🔄 Reboot Pi</button>
            <button onclick="confirmSystemAction('pi_shutdown')" class="btn-shutdown">⏻ Shutdown Pi</button>
        </div>
        <div id="action-status"></div>
    </div>

    <div class="panel">
        <div class="panel-title">LIVE AIRCRAFT - 200 NM AROUND SHAWNEE</div>
        <div class="adsb-stats">
            <span>AIRCRAFT IN RANGE: <b id="adsb-count">...</b></span>
            <span>NEAREST: <b id="adsb-nearest">...</b></span>
            <span>PRIORITY: <b id="adsb-priority">...</b></span>
        </div>
        <div id="map"></div>
        <div class="adsb-updated" id="adsb-updated">Loading aircraft...</div>
    </div>
    <div class="panel">
        <div class="panel-title">AIRCRAFT LIST - NEAREST FIRST</div>
        <div id="aircraft-list"><div class="qa-empty">Loading aircraft...</div></div>
    </div>

    <div class="panel">
        <div class="panel-title">GEMINI POOL</div>
        <div class="stat-line">ACTIVE KEY: <b id="pool-key">...</b></div>
        <div class="stat-line">RECENT REPLIES: <b id="pool-calls">...</b></div>
        <div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div>
    </div>

    <div class="panel">
        <div class="panel-title">RECENT QUESTIONS &amp; ANSWERS</div>
        <div id="qa-list"><div class="qa-empty">Loading...</div></div>
    </div>

    <div class="filter-row"><label><input type="checkbox" id="hide-ami" checked> Hide AMI events in log</label></div>
    <div id="terminal"></div>

    <script>
        const terminal = document.getElementById('terminal');
        const _amiBox = document.getElementById('hide-ami');
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
        const statusDiv = document.getElementById('action-status');
        const linksRender = document.getElementById('links-render');

        let authToken = localStorage.getItem('node_dashboard_token') || '';

        document.addEventListener("DOMContentLoaded", function() {
            if (authToken) {
                document.getElementById('lock-overlay').style.display = 'none';
            }

            document.getElementById('pass-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    unlockControls();
                }
            });

            // Spin up background network connection monitoring query loop
            pollConnectedNodes();
            setInterval(pollConnectedNodes, 4000);
        });

        function unlockControls() {
            const passValue = document.getElementById('pass-input').value;
            if (!passValue.trim()) return;
            authToken = passValue;
            localStorage.setItem('node_dashboard_token', passValue);
            document.getElementById('lock-overlay').style.display = 'none';
        }

        function pollConnectedNodes() {
            fetch('/api/connections')
            .then(res => res.json())
            .then(data => {
                if(data.status === "standalone") {
                    linksRender.innerHTML = `☐ CONNECTIONS: <span style="color: #8b949e;">NO CONNECTION</span>`;
                } else if(data.status === "active") {
                    linksRender.innerHTML = `☐ CONNECTIONS: <span class="node-active">${data.nodes.join(', ')}</span>`;
                } else {
                    linksRender.innerHTML = `☐ CONNECTIONS: <span style="color: #da3637;">OFFLINE</span>`;
                }
            })
            .catch(() => {
                linksRender.innerHTML = `☐ CONNECTIONS: <span style="color: #da3637;">TIMEOUT</span>`;
            });
        }

        const eventSource = new EventSource('/stream');
        eventSource.onmessage = function(event) {
            if (event.data.trim() === "") return;
            var _ha = document.getElementById('hide-ami');
            if (_ha && _ha.checked && event.data.indexOf('[AMI EVENT]') !== -1) return;
            const line = document.createElement('div');
            line.className = 'log-line';
            line.textContent = event.data;
            terminal.appendChild(line);
            terminal.scrollTop = terminal.scrollHeight;
        };

        function triggerAction(actionName) {
            statusDiv.textContent = `Sending: ${actionName}...`;

            fetch(`/action/${actionName}`, {
                method: 'GET',
                headers: { 'X-Admin-Key': authToken }
            })
            .then(res => {
                if (res.status === 401) {
                    localStorage.removeItem('node_dashboard_token');
                    authToken = '';
                    document.getElementById('pass-input').value = '';
                    document.getElementById('lock-overlay').style.display = 'flex';
                    statusDiv.textContent = '🔒 Session Rejected: Unauthorized Verification Required';
                    throw new Error('Unauthorized');
                }
                return res.json();
            })
            .then(data => {
                statusDiv.textContent = data.message;
                setTimeout(() => { statusDiv.textContent = ''; }, 4000);
            })
            .catch(err => {
                if(err.message !== 'Unauthorized') {
                    statusDiv.textContent = 'Execution Error';
                }
            });
        }

        function confirmSystemAction(actionName) {
            const prettyName = actionName === 'pi_reboot' ? 'REBOOT' : 'SHUTDOWN';
            if (confirm(`CRITICAL WARNING: Are you sure you want to completely ${prettyName} the host Raspberry Pi hardware?`)) {
                triggerAction(actionName);
            }
        }

        // --- DASHBOARD UPGRADE: MAP / STATUS / Q&A ---
        let adsbMap = null;
        let adsbMarkers = {};
        function initAdsbMap() {
            if (typeof L === 'undefined') return;
            if (!document.getElementById('map')) return;
            adsbMap = L.map('map', {maxZoom: 19}).setView([38.99, -94.76], 8);
            adsbMap.on('click', function(){
                if (Date.now() - (adsbMap._lastMkClick || 0) < 300) return;
                Object.keys(adsbMarkers).forEach(function(k){ adsbMarkers[k].setOpacity(1); });
                if (adsbMap._routeFromLine) { adsbMap.removeLayer(adsbMap._routeFromLine); adsbMap._routeFromLine = null; }
                if (adsbMap._routeToLine) { adsbMap.removeLayer(adsbMap._routeToLine); adsbMap._routeToLine = null; }
                if (adsbMap._trailLine) { adsbMap.removeLayer(adsbMap._trailLine); adsbMap._trailLine = null; }
                if (adsbMap._fwdLine) { adsbMap.removeLayer(adsbMap._fwdLine); adsbMap._fwdLine = null; }
            });
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, maxNativeZoom: 19, attribution: '&copy; OpenStreetMap contributors'}).addTo(adsbMap);
            L.marker([38.99, -94.76]).addTo(adsbMap).bindPopup('KFORIZ hub - Shawnee, KS');
            var rangeRing = L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6', interactive: false}).addTo(adsbMap);
            function _toggleRing(){ if (adsbMap.getZoom() > 12) { if (adsbMap.hasLayer(rangeRing)) adsbMap.removeLayer(rangeRing); } else { if (!adsbMap.hasLayer(rangeRing)) rangeRing.addTo(adsbMap); } }
            adsbMap.on('zoomend', _toggleRing); _toggleRing();
            // Labelled places: airports, civic buildings, fire stations.
            var PLACES = [
                {name: 'MCI', lat: 39.2982, lon: -94.71513, cls: 'ap-label'},
                {name: 'New Century', lat: 38.8389, lon: -94.89602, cls: 'ap-label'},
                {name: 'Olathe Exec', lat: 38.85441, lon: -94.73514, cls: 'ap-label'},
                {name: 'Downtown', lat: 39.13156, lon: -94.58741, cls: 'ap-label'},
                {name: "Lee's Summit", lat: 38.96205, lon: -94.37537, cls: 'ap-label'},
                {name: 'Shawnee PD', lat: 39.02386, lon: -94.78227, cls: 'poi-label', ay: -22},
                {name: 'Shawnee City Hall', lat: 39.0234, lon: -94.71521, cls: 'poi-label'},
                {name: 'Fire 71', lat: 39.010516, lon: -94.722653, cls: 'fire-label'},
                {name: 'Fire 72', lat: 39.023828, lon: -94.780433, cls: 'fire-label', ay: 14},
                {name: 'Fire 73', lat: 39.00577, lon: -94.85761, cls: 'fire-label'},
                {name: 'Fire 74', lat: 39.0323, lon: -94.84965, cls: 'fire-label'}
            ];
            PLACES.forEach(function(p){ var anch = (typeof p.ay === 'number') ? [0, p.ay] : [0, 0]; L.marker([p.lat, p.lon], {icon: L.divIcon({className: 'place-marker', html: '<div class="' + p.cls + '">' + p.name + '</div>', iconSize: null, iconAnchor: anch})}).addTo(adsbMap).bindPopup('<div style="font-size:20px;font-weight:bold;">' + p.name + '</div>' + '<div style="font-size:13px;color:#8b949e;">' + (p.cls === 'fire-label' ? 'Fire Station' : (p.cls === 'ap-label' ? 'Airport' : (p.name.indexOf('PD') !== -1 ? 'Police Department' : 'City Hall'))) + '</div>'); });
            // Fullscreen map toggle (button bottom-right, exit top-right.
            var fsBtn = document.createElement('button');
            fsBtn.className = 'map-fs-btn'; fsBtn.textContent = '⛶'; fsBtn.title = 'Full screen';
            fsBtn.onclick = function(){ var m = document.getElementById('map'); m.classList.add('map-fullscreen'); fsBtn.style.display = 'none'; document.getElementById('map-fs-exit').classList.add('map-fs-show'); (function(){ function refit(){ adsbMap.invalidateSize(); try{ adsbMap.dragging.enable(); adsbMap.touchZoom.enable(); adsbMap.scrollWheelZoom.enable(); adsbMap.doubleClickZoom.enable(); }catch(e){} } refit(); requestAnimationFrame(refit); setTimeout(refit, 150); setTimeout(refit, 400); })(); };
            document.getElementById('map').appendChild(fsBtn);
            var fsExit = document.createElement('button');
            fsExit.id = 'map-fs-exit'; fsExit.className = 'map-fs-exit'; fsExit.textContent = '×'; fsExit.title = 'Exit full screen';
            fsExit.onclick = function(){ var m = document.getElementById('map'); m.classList.remove('map-fullscreen'); fsExit.classList.remove('map-fs-show'); fsBtn.style.display = 'flex'; (function(){ function refit(){ adsbMap.invalidateSize(); try{ adsbMap.dragging.enable(); adsbMap.touchZoom.enable(); adsbMap.scrollWheelZoom.enable(); adsbMap.doubleClickZoom.enable(); }catch(e){} } refit(); requestAnimationFrame(refit); setTimeout(refit, 150); setTimeout(refit, 400); })(); };
            window.addEventListener('resize', function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } });
            window.addEventListener('orientationchange', function(){ setTimeout(function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } }, 200); });
            if (window.visualViewport) { window.visualViewport.addEventListener('resize', function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } }); }
            document.body.appendChild(fsExit);
        }
        function fmtAlt(a) {
            if (a === null || a === undefined) return 'n/a';
            return Math.round(a).toLocaleString() + ' ft';
        }
        function fmtSpd(s) {
            if (s === null || s === undefined) return 'n/a';
            return Math.round(s) + ' kt';
        }
        function renderAircraftList(list) {
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
                const mkey = a.reg || a.callsign;
                const clickable = (a.lat !== null && a.lat !== undefined && a.lon !== null && a.lon !== undefined) ? ' data-lat="' + a.lat + '" data-lon="' + a.lon + '" data-key="' + mkey + '" onclick="focusAircraft(this)" title="Tap to show on map"' : '';
                html += '<tr' + cls + clickable + '><td>' + a.callsign + '</td><td>' + (a.type || '-') + '</td><td>' + fmtAlt(a.alt) + '</td><td>' + fmtSpd(a.spd) + '</td><td>' + dist + '</td></tr>';
            });
            html += '</table>';
            if (sorted.length > 20) {
                html += '<div class="adsb-updated">Showing nearest 20 of ' + sorted.length + ' aircraft.</div>';
            }
            el.innerHTML = html;
        }
        function focusAircraft(row) {
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
                const temp = (d.temp_c !== null && d.temp_c !== undefined) ? d.temp_c.toFixed(1) + '°C' : '-';
                const load = (d.load1 !== null && d.load1 !== undefined) ? d.load1.toFixed(2) : '-';
                const up = (d.uptime_s !== null && d.uptime_s !== undefined) ? fmtUptime(d.uptime_s) : '-';
                const disk = (d.disk_free_gb !== null && d.disk_free_gb !== undefined) ? Math.round(d.disk_free_gb) + ' GB free' : '-';
                el.textContent = 'TEMP ' + temp + ' | LOAD ' + load + ' | UP ' + up + ' | DISK ' + disk;
            }).catch(function(){});
        }
        function aircraftIcon(a) {
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
                renderAircraftList(data.aircraft);
                if (!adsbMap) return;
                const seen = {};
                data.aircraft.forEach(function(a){
                    const key = a.reg || a.callsign;
                    seen[key] = true;
                    const popup = '<b>' + a.callsign + '</b><br>' + (a.reg || '') + ' ' + (a.type || '') + '<br>Alt ' + fmtAlt(a.alt) + ' - ' + fmtSpd(a.spd) + (a.priority ? '<br><b>PRIORITY</b>' : '');
                    if (adsbMarkers[key]) {
                        adsbMarkers[key].setLatLng([a.lat, a.lon]);
                        adsbMarkers[key].setPopupContent(popup);
                    } else {
                        const m = L.marker([a.lat, a.lon], {icon: aircraftIcon(a)}).addTo(adsbMap);
                        m.bindPopup(popup);
                        adsbMarkers[key] = m;
                        var AIRPORT_COORDS = {
                            'ATL': [33.6407, -84.4277], 'LAX': [33.9416, -118.4085], 'ORD': [41.9742, -87.9073],
                            'DFW': [32.8998, -97.0403], 'DEN': [39.8561, -104.6737], 'JFK': [40.6413, -73.7781],
                            'SFO': [37.6213, -122.3790], 'SEA': [47.4502, -122.3088], 'LAS': [36.0840, -115.1537],
                            'MCO': [28.4312, -81.3081], 'EWR': [40.6895, -74.1745], 'CLT': [35.2144, -80.9473],
                            'MIA': [25.7959, -80.2870], 'PHX': [33.4373, -112.0078], 'IAH': [29.9902, -95.3368],
                            'BOS': [42.3656, -71.0096], 'MSP': [44.8848, -93.2223], 'DTW': [42.2124, -83.3534],
                            'PHL': [39.8744, -75.2424], 'LGA': [40.7769, -73.8740], 'BWI': [39.1754, -76.6684],
                            'SLC': [40.7899, -111.9791], 'SAN': [32.7338, -117.1933], 'IAD': [38.9531, -77.4565],
                            'DCA': [38.8512, -77.0402], 'MDW': [41.7868, -87.7522], 'TPA': [27.9755, -82.5332],
                            'PDX': [45.5898, -122.5951], 'STL': [38.7487, -90.3700], 'BNA': [36.1263, -86.6774],
                            'AUS': [30.1975, -97.6664], 'MSY': [29.9934, -90.2580], 'RDU': [35.8776, -78.7875],
                            'SMF': [38.6954, -121.5908], 'MCI': [39.2982, -94.7151], 'MEM': [35.0424, -89.9767],
                            'OMA': [41.3032, -95.8941], 'DSM': [41.5340, -93.6631], 'ICT': [37.6499, -97.4331],
                            'TUL': [36.1984, -95.8881], 'OKC': [35.3931, -97.6007], 'SNA': [33.6757, -117.8682],
                            'HYS': [38.8440, -99.2738], 'IXD': [38.8389, -94.8960], 'OJC': [38.8544, -94.7351],
                            'MKC': [39.1316, -94.5874], 'LXT': [38.9621, -94.3754], 'CMH': [39.9980, -82.8919],
                            'IND': [39.7173, -86.2944], 'PIT': [40.4915, -80.2329], 'CLE': [41.4117, -81.8498],
                            'LIT': [34.7294, -92.2243], 'HSV': [34.6372, -86.7751], 'BHM': [33.5629, -86.7535],
                            'GSO': [36.0978, -79.9373], 'RIC': [37.5052, -77.3197], 'ORF': [36.8946, -76.2012],
                            'PVD': [41.7240, -71.4282], 'ALB': [42.7483, -73.8017], 'BUF': [42.9405, -78.7322],
                            'ROC': [43.1189, -77.6724], 'SYR': [43.1112, -76.1063], 'GRR': [42.8808, -85.5228],
                            'MSN': [43.1399, -89.3375]
                        };
                        (function(mk, ac){ mk.on('click', function(){
                            var hx = (ac.hex || ac.reg || ac.callsign || '').toLowerCase();
                            if (!hx) return;
                            var trailP = fetch('/api/trail/' + encodeURIComponent(hx)).then(function(r){ return r.json(); });
                            var routeP = fetch('/api/route/' + encodeURIComponent(hx)).then(function(r){ return r.json(); }).catch(function(){ return {}; });
                            Promise.all([trailP, routeP]).then(function(res){
                                var d = res[0], rt = res[1] || {};
                                if (adsbMap._trailLine) { adsbMap.removeLayer(adsbMap._trailLine); adsbMap._trailLine = null; }
                                if (adsbMap._fwdLine) { adsbMap.removeLayer(adsbMap._fwdLine); adsbMap._fwdLine = null; }
                                if (d.trail && d.trail.length > 1) { adsbMap._trailLine = L.polyline(d.trail, {color: '#58a6ff', weight: 4, interactive: false}).addTo(adsbMap); }
                                if (d.forward && d.forward.length > 0) { var fp = [[ac.lat, ac.lon]].concat(d.forward); adsbMap._fwdLine = L.polyline(fp, {color: '#3fb950', weight: 4, dashArray: '6 6', interactive: false}).addTo(adsbMap); }
                                adsbMap._lastMkClick = Date.now();
                                Object.keys(adsbMarkers).forEach(function(k){ if (adsbMarkers[k] !== mk) { adsbMarkers[k].setOpacity(0.12); } else { adsbMarkers[k].setOpacity(1); } });
                                if (adsbMap._routeFromLine) { adsbMap.removeLayer(adsbMap._routeFromLine); adsbMap._routeFromLine = null; }
                                if (adsbMap._routeToLine) { adsbMap.removeLayer(adsbMap._routeToLine); adsbMap._routeToLine = null; }
                                if (rt.origin && rt.destination) {
                                    var _oc = AIRPORT_COORDS[rt.origin], _dc = AIRPORT_COORDS[rt.destination];
                                    if (_oc) { adsbMap._routeFromLine = L.polyline([_oc, [ac.lat, ac.lon]], {color: '#e3b341', weight: 3, interactive: false}).addTo(adsbMap); }
                                    if (_dc) { adsbMap._routeToLine = L.polyline([[ac.lat, ac.lon], _dc], {color: '#58a6ff', weight: 3, dashArray: '8 6', interactive: false}).addTo(adsbMap); }
                                }
                            });
                            var info = (ac.callsign || ac.reg || hx) + (ac.type ? ' (' + ac.type + ')' : '') + '<br>Alt ' + (ac.alt ? ac.alt.toLocaleString() + ' ft' : '-') + ' &nbsp; Spd ' + (ac.spd ? ac.spd + ' kt' : '-');
                            if (rt.origin && rt.destination) { info += '<br>Route' + (rt.live ? '' : ' (last flight)') + ': ' + rt.origin + ' &rarr; ' + rt.destination; }
                            L.popup().setLatLng([ac.lat, ac.lon]).setContent(info).openOn(adsbMap);
                        }); })(m, a);
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
                const lk = document.getElementById('ai-last-keyup');
                if (lk) lk.textContent = data.last_keyup || '-';
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
            pollHealth();
            setInterval(pollHealth, 30000);
        });
    </script>
</body>
</html>
"""
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/api/connections')
def connections_api():
    try:
        res = subprocess.run(['sudo', 'asterisk', '-rx', 'rpt nodes 625731'], capture_output=True, text=True, timeout=3)

        discovered_nodes = []
        for line in res.stdout.splitlines():
            tokens = line.strip().split()
            for token in tokens:
                clean = re.sub(r'^[^A-Z0-9]+|[^A-Z0-9]+$', '', token.upper())
                clean_node = re.sub(r'^[A-Z](?=\d{4,6}$)', '', clean)

                if clean_node.isdigit() and 4 <= len(clean_node) <= 6:
                    if clean_node not in ['625731', '4569']:
                        if clean_node not in discovered_nodes:
                            discovered_nodes.append(clean_node)

        if discovered_nodes:
            discovered_nodes.sort()
            return jsonify({"status": "active", "nodes": discovered_nodes})
        return jsonify({"status": "standalone", "nodes": []})
    except Exception:
        return jsonify({"status": "error", "nodes": []})

def _tail_log(n=300):
    try:
        res = subprocess.run(['tail', '-n', str(n), '/var/log/ai_orchestrator.log'], capture_output=True, text=True, errors='replace', timeout=5)
        return res.stdout.splitlines()
    except Exception:
        return []
def _log_time(line):
    m = re.search(r'\((\d{2}:\d{2}:\d{2})\)', line)
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
    last_keyup = ""
    for line in reversed(_tail_log(300)):
        if "[WHISPER GATE]" in line or "[RADIO INTERPRETATION]" in line:
            last_keyup = _log_time(line)
            break
    return jsonify({"status": status, "started": started, "last_reply": last_reply, "last_keyup": last_keyup})

@app.route('/api/pool')
def pool_api():
    active_key = "-"
    recent_calls = 0
    last_failover = ""
    for line in _tail_log(300):
        if "[GEMINI RESPONSE]" in line:
            recent_calls += 1
        m = re.search(r'Key Pool Index \[(\d+)\]', line)
        if m:
            active_key = m.group(1)
        m = re.search(r'Key (\d+) submitted', line)
        if m:
            active_key = m.group(1)
        low = line.lower()
        if "failover" in low or "pool exhaustion" in low:
            last_failover = _log_time(line) or "recent"
    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover})

@app.route('/api/health')
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

@app.route('/api/trail/<hx>')
def api_trail(hx):
    hx = (hx or '').lower()
    _now = time.time()
    _pts = [[p[0], p[1]] for p in _trail.get(hx, []) if _now - p[2] <= 1800]
    _fwd = []
    _ac = None
    for _a in _aircraft_cache['aircraft']:
        if _a.get('hex') == hx:
            _ac = _a; break
    if _ac is not None and _ac.get('lat') is not None and _ac.get('lon') is not None:
        _trk = _ac.get('track'); _gs = _ac.get('spd')
        if _trk is not None and _gs:
            _la0 = float(_ac['lat']); _lo0 = float(_ac['lon'])
            _rad = math.radians(float(_trk))
            for _mins in (5, 10, 20, 30):
                _dist = float(_gs) * (_mins / 60.0)
                _dla = _dist * math.cos(_rad) / 60.0
                _dlo = _dist * math.sin(_rad) / (60.0 * max(0.2, math.cos(math.radians(_la0))))
                _fwd.append([_la0 + _dla, _lo0 + _dlo])
    return jsonify({'hex': hx, 'trail': _pts, 'forward': _fwd, 'aircraft': _ac})

@app.route('/api/route/<hx>')
def api_route(hx):
    hx = (hx or '').lower()
    now = int(time.time())
    ent = _route_cache.get(hx)
    if ent and now - ent[0] < 600:
        return jsonify(ent[1])
    origin = None; dest = None; live = False
    _cs = None
    for _a in _aircraft_cache.get('aircraft') or []:
        if (_a.get('hex') or '') == hx:
            _cs = (_a.get('callsign') or '').strip()
            break
    if _cs:
        _o, _d = _aviation_route(_cs)
        if _o and _d:
            origin, dest, live = _o, _d, True
    if not (origin and dest):
        try:
            begin = now - 86400
            url = 'https://opensky-network.org/api/flights/aircraft?icao24=%s&begin=%d&end=%d' % (hx, begin, now)
            req = urllib.request.Request(url, headers={'User-Agent': 'KFORIZ-hub-dashboard/1.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                flights = json.load(resp)
            if flights:
                f = max(flights, key=lambda x: x.get('lastSeen') or 0)
                origin = f.get('estDepartureAirport')
                dest = f.get('estArrivalAirport')
        except Exception:
            pass
    out = {'hex': hx, 'origin': origin, 'destination': dest, 'live': live}
    _route_cache[hx] = (now, out)
    return jsonify(out)

@app.route('/stream')
def stream():
    def generate():
        process = subprocess.Popen(
            ['tail', '-n', '40', '-f', '/var/log/ai_orchestrator.log'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        while True:
            line = process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield f"data: {line.strip()}\n\n"
    return Response(generate(), mimetype='text/event-stream')

@app.route('/action/<action_cmd>')
def handle_action(action_cmd):
    incoming_key = request.headers.get('X-Admin-Key', '')
    if incoming_key != DASHBOARD_PASSWORD:
        return jsonify({"status": "error", "message": "Authentication Key Signature Mismatch"}), 401

    try:
        if action_cmd == 'id_node':
            timestamp = int(time.time())
            id_text = "This is the K F O R I Z... Artificial Intelligence Hub."
            estimated_duration = (len(id_text) * 0.08) + 6.0
            cooldown_until = time.time() + estimated_duration
            try:
                with open("/tmp/ai_dash_cooldown", "w") as f:
                    f.write(str(cooldown_until))
            except Exception:
                pass
            output_wav = f"/var/lib/asterisk/sounds/ai_dash_id_{timestamp}.wav"
            temp_wav = f"/tmp/dash_id_{timestamp}.wav"

            echo_proc = subprocess.Popen(["echo", id_text], stdout=subprocess.PIPE)
            piper_proc = subprocess.Popen(
                ["/usr/local/bin/piper", "--model", "/opt/piper/en_US-amy-medium.onnx", "--output_file", temp_wav],
                stdin=echo_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            echo_proc.stdout.close()
            piper_proc.communicate()
            if os.path.exists(temp_wav):
                ffmpeg_cmd = ["ffmpeg", "-y", "-i", temp_wav, "-ar", "8000", "-ac", "1", output_wav]
                subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                os.chmod(output_wav, 0o644)
                file_base = os.path.splitext(output_wav)[0]
                subprocess.run(['sudo', 'asterisk', '-rx', f'rpt playback 625731 {file_base}'], check=True)
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
                return jsonify({"status": "success", "message": "🔊 Manual Piper ID Generated & Dispatched Over-Air"})
            else:
                return jsonify({"status": "error", "message": "⚠️ Local Piper engine failed to output raw wave voice"})
        elif action_cmd == 'ai_start':
            subprocess.run(['sudo', 'systemctl', 'start', 'ai_orchestrator.service'], check=True)
            return jsonify({"status": "success", "message": "▶ AI Service Signal Sent: START"})
        elif action_cmd == 'ai_stop':
            subprocess.run(['sudo', 'systemctl', 'stop', 'ai_orchestrator.service'], check=True)
            return jsonify({"status": "success", "message": "⏹ AI Service Signal Sent: STOP"})
        elif action_cmd == 'ai_restart':
            subprocess.run(['sudo', 'systemctl', 'restart', 'ai_orchestrator.service'], check=True)
            return jsonify({"status": "success", "message": "🔄 AI Service Cycle Initiated"})
        elif action_cmd == 'pi_reboot':
            subprocess.Popen(['sudo', 'systemctl', 'reboot'])
            return jsonify({"status": "success", "message": "🔄 Hardware Reboot Command Dispatched..."})
        elif action_cmd == 'pi_shutdown':
            subprocess.Popen(['sudo', 'systemctl', 'poweroff'])
            return jsonify({"status": "success", "message": "⏻ Hardware Poweroff Command Dispatched..."})
        return jsonify({"status": "unknown", "message": "⚠ Unrecognized command parameter"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"⚠ Execution Failed: {str(e)}"}, 500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=62573, debug=False)
