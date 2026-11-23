import os
import time
import subprocess
import re
import threading
import json
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
            "category": a.get("category"),
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

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KF0RIZ // AI Hub Live Telemetry</title>
<style>
body { background-color: #0d1117; color: #c9d1d9; font-family: 'Courier New', Courier, monospace; margin: 0; padding: 20px; display: flex; flex-direction: column; min-height: 100vh; box-sizing: border-box;}
header { flex-shrink: 0; background-color: #161b22; padding: 15px; border-radius: 6px; border: 1px solid #30363d; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;}
.brand-block { display: flex; flex-direction: column; gap: 4px;}
h1 { margin: 0; font-size: 1.2rem; color: #58a6ff; letter-spacing: 1px;}
/* Live Node Link Tracker Style */
.node-matrix { color: #8b949e; font-size: 0.85rem; font-weight: bold; letter-spacing: 0.5px;}
.node-active { color: #58a6ff;}
.status { color: #7fe7c4; font-weight: bold; font-size: 0.9rem;}
.control-panel { flex-shrink: 0; background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 6px; margin-bottom: 15px; display: flex; flex-direction: column; gap: 12px; position: relative;}
.control-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; width: 100%; max-width: 600px;}
button { color: #ffffff; border: 1px solid #f0f6fc1f; padding: 10px 14px; border-radius: 6px; cursor: pointer; font-weight: bold; font-family: sans-serif; font-size: 0.88rem; transition: background 0.15s, border-color 0.15s; width: 100%; box-sizing: border-box; display: flex; align-items: center; justify-content: center; gap: 6px;}
/* --- ACCENT COLOR PALETTE --- */
.btn-id { background-color: #1f6feb;} /* Blue */
.btn-id:hover { background-color: #388bfd; border-color: #8b949e;}
.btn-restart { background-color: #d29922;} /* Amber */
.btn-restart:hover { background-color: #e3b341; border-color: #8b949e;}
.btn-start { background-color: #238636;} /* Green */
.btn-start:hover { background-color: #2ea043; border-color: #8b949e;}
.btn-stop { background-color: #da3637;} /* Red */
.btn-stop:hover { background-color: #f85149; border-color: #8b949e;}
.btn-reboot { background-color: #8957e5;} /* Purple */
.btn-reboot:hover { background-color: #a371f7; border-color: #8b949e;}
.btn-shutdown { background-color: #484f58;} /* Muted Slate */
.btn-shutdown:hover { background-color: #6e7681; border-color: #8b949e;}
#terminal { height: 320px; flex-shrink: 0; background-color: #010409; border: 1px solid #30363d; border-radius: 6px; padding: 15px; overflow-y: auto; white-space: pre-wrap; font-size: 0.9rem; line-height: 1.5; box-shadow: inset 0 0 10px rgba(0,0,0,0.8);}
.log-line { margin-bottom: 4px; border-bottom: 1px solid #161b22; padding-bottom: 2px;}
#action-status { color: #e3b341; font-weight: bold; font-size: 0.9rem; min-height: 18px;}
.lock-wall { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(22, 27, 34, 0.98); backdrop-filter: blur(5px); display: flex; justify-content: center; align-items: center; border-radius: 6px; gap: 14px; box-sizing: border-box; padding: 15px; z-index: 100;}
.lock-title { color: #e3b341; font-weight: bold; font-family: sans-serif; font-size: 0.85rem; letter-spacing: 0.5px;}
.lock-input { background-color: #010409; color: #c9d1d9; border: 1px solid #30363d; padding: 8px 12px; border-radius: 6px; font-family: monospace; font-size: 0.85rem; outline: none; max-width: 200px;}
@media (max-width: 768px) { body { padding: 10px;}.control-row { max-width: 100%;} button { padding: 12px; font-size: 0.95rem;}.lock-wall { flex-direction: column; justify-content: center; text-align: center; gap: 10px; height: 100%;}.lock-input,.lock-wall button { width: 90%; max-width: 280px; padding: 11px; text-align: center; font-size: 1rem;}}
/* --- DASHBOARD UPGRADE: MAP / STATUS / Q&A PANELS --- */
.panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; margin-bottom: 15px;}
.ap-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #58a6ff; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap;}
.poi-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #d29922; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap;}
.fire-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #f85149; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap;}
.map-fullscreen { position: fixed!important; inset: 0!important; width: 100vw!important; width: 100dvw!important; height: 100vh!important; height: 100dvh!important; z-index: 1000!important; border-radius: 0!important; margin: 0!important; padding: 0!important; border: none!important;}
.map-fs-btn { position: absolute!important; right: 10px!important; bottom: 10px!important; z-index: 1001!important; width: auto!important; min-width: 0!important; display: flex!important; align-items: center!important; justify-content: center!important; background: rgba(13,17,23,0.55)!important; color: #e6edf3!important; border: 1px solid rgba(230,237,243,0.35)!important; border-radius: 6px!important; padding: 6px 9px!important; font-size: 18px!important; line-height: 1!important; font-weight: 700!important; cursor: pointer!important;}
.map-fs-exit { position: fixed!important; right: 10px!important; top: 10px!important; z-index: 1002!important; width: auto!important; min-width: 0!important; display: none!important; align-items: center!important; justify-content: center!important; background: rgba(13,17,23,0.55)!important; color: #e6edf3!important; border: 1px solid rgba(230,237,243,0.35)!important; border-radius: 6px!important; padding: 6px 10px!important; font-size: 18px!important; line-height: 1!important; font-weight: 700!important; cursor: pointer!important;}
.map-fs-exit.map-fs-show { display: flex!important;}
.panel-title { color: #58a6ff; font-weight: bold; font-size: 0.95rem; letter-spacing: 0.5px; margin-bottom: 10px; font-family: sans-serif;}
#map { height: 320px; width: 100%; border-radius: 6px; border: 1px solid #30363d; background: #010409; z-index: 1;}
.adsb-stats { display: flex; gap: 16px; flex-wrap: wrap; color: #8b949e; font-size: 0.85rem; font-weight: bold; margin-bottom: 10px;}
.adsb-stats b { color: #e3b341;}
.adsb-updated { color: #8b949e; font-size: 0.8rem; margin-top: 8px;}
.stat-grid { display: grid; grid-template-columns: 1fr; gap: 15px; margin-bottom: 15px;}
.stat-box { margin-bottom: 0;}
.stat-line { color: #c9d1d9; font-size: 0.9rem; margin: 4px 0;}
.stat-line b { color: #7fe7c4;}
.qa-item { border-bottom: 1px solid #161b22; padding: 8px 0;}
.qa-item:last-child { border-bottom: none;}
.qa-q { color: #58a6ff; font-size: 0.9rem;}
.qa-a { color: #c9d1d9; font-size: 0.9rem;}
.qa-time { color: #8b949e; font-size: 0.8rem;}
.qa-empty { color: #8b949e; font-size: 0.9rem;}
.filter-row { display: flex; align-items: center; gap: 8px; color: #8b949e; font-size: 0.85rem; font-family: sans-serif; margin-bottom: 8px;}
.filter-row input { width: 18px; height: 18px;}
.adsb-marker { background: transparent; border: none;}
@media (min-width: 769px) { body { max-width: 1100px; margin: 0 auto;} #map { height: 420px;} #terminal { height: 420px;}.stat-grid { grid-template-columns: 1fr 1fr;}}
.ac-table { width: 100%; border-collapse: collapse; font-size: 0.85rem;}
.ac-table th { color: #8b949e; text-align: left; padding: 4px 6px; border-bottom: 1px solid #30363d; font-family: sans-serif; font-size: 0.8rem;}
.ac-table td { padding: 4px 6px; border-bottom: 1px solid #161b22; color: #c9d1d9;}
.ac-table tr.ac-pri td { color: #f85149; font-weight: bold;}
.ac-table tr[data-lat] { cursor: pointer;}
.ac-table tr[data-lat]:hover td { background: #21262d;}
#aircraft-list { max-height: 260px; overflow-y: auto;}
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
<header>
<div class="brand-block">
<h1>[KF0RIZ] Allstar VoIP AI Orchestrator</h1>
<div id="links-render" class="node-matrix">🔗 CONNECTIONS: <span style="color: #e3b341;">POLLING ASTERISK...</span></div>
</div>
<div class="status">● LIVE TELEMETRY STREAMING</div>
</header>
<div class="panel"><div class="panel-title">AI SERVICE</div><div class="stat-line">STATUS: <b id="ai-status">...</b></div><div class="stat-line">STARTED: <b id="ai-started">...</b></div><div class="stat-line">LAST REPLY: <b id="ai-last-reply">...</b></div><div class="stat-line">LAST KEY-UP: <b id="ai-last-keyup">...</b></div></div>
<div class="panel"><div class="panel-title">HUB HEALTH</div><div class="stat-line" id="hub-health">Loading...</div></div>
<div class="control-panel"><div id="lock-overlay" class="lock-wall"><span class="lock-title">🔒 SYSTEM CONSOLE LOCKED</span><input type="password" id="pass-input" class="lock-input" placeholder="Enter Control Key..."><button onclick="unlockControls()" class="btn-start" style="width: auto;">Unlock</button></div>
<div class="control-row"><button onclick="triggerAction('id_node')" class="btn-id">🔊 ID Node</button><button onclick="triggerAction('ai_restart')" class="btn-restart">🔄 Restart AI</button></div>
<div class="control-row"><button onclick="triggerAction('ai_start')" class="btn-start">▶ Start AI</button><button onclick="triggerAction('ai_stop')" class="btn-stop">🛑 Stop AI</button></div>
<div class="control-row"><button onclick="confirmSystemAction('pi_reboot')" class="btn-reboot">🌀 Reboot Pi</button><button onclick="confirmSystemAction('pi_shutdown')" class="btn-shutdown">🔌 Shutdown Pi</button></div><div id="action-status"></div></div>
<div class="panel"><div class="panel-title">LIVE AIRCRAFT - 200 NM AROUND SHAWNEE</div><div class="adsb-stats"><span>AIRCRAFT IN RANGE: <b id="adsb-count">...</b></span><span>NEAREST: <b id="adsb-nearest">...</b></span><span>PRIORITY: <b id="adsb-priority">...</b></span></div><div id="map"></div><div class="adsb-updated" id="adsb-updated">Loading aircraft...</div></div>
<div class="panel"><div class="panel-title">AIRCRAFT LIST - NEAREST FIRST</div><div id="aircraft-list"><div class="qa-empty">Loading aircraft...</div></div></div>
<div class="panel"><div class="panel-title">GEMINI POOL</div><div class="stat-line">ACTIVE KEY: <b id="pool-key">...</b></div><div class="stat-line">RECENT REPLIES: <b id="pool-calls">...</b></div><div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div></div>
<div class="panel"><div class="panel-title">RECENT QUESTIONS &amp; ANSWERS</div><div id="qa-list"><div class="qa-empty">Loading...</div></div></div>
<div class="filter-row"><label><input type="checkbox" id="hide-ami" checked> Hide AMI events in log</label></div><div id="terminal"></div><script>
const terminal = document.getElementById('terminal');
const _amiBox = document.getElementById('hide-ami'); if (_amiBox) { const _savedAmi = localStorage.getItem('hide_ami'); if (_savedAmi !== null) { _amiBox.checked = (_savedAmi === 'true');} _amiBox.addEventListener('change', function() { localStorage.setItem('hide_ami', this.checked ? 'true' : 'false'); const hide = this.checked; document.querySelectorAll('#terminal.log-line').forEach(function(el) { if (el.textContent.indexOf('[AMI EVENT]') !== -1) { el.style.display = hide ? 'none' : '';}});});}
const statusDiv = document.getElementById('action-status'); const linksRender = document.getElementById('links-render'); let authToken = localStorage.getItem('node_dashboard_token') || '';
document.addEventListener("DOMContentLoaded", function() { if (authToken) { document.getElementById('lock-overlay').style.display = 'none';} document.getElementById('pass-input').addEventListener('keypress', function(e) { if (e.key === 'Enter') { unlockControls();}}); // Spin up background network connection monitoring query loop pollConnectedNodes(); setInterval(pollConnectedNodes, 4000);});
function unlockControls() { const passValue = document.getElementById('pass-input').value; if (!passValue.trim()) return; authToken = passValue; localStorage.setItem('node_dashboard_token', passValue); document.getElementById('lock-overlay').style.display = 'none';}
function pollConnectedNodes() { fetch('/api/connections').then(res => res.json()).then(data => { if (data.status === "standalone") { linksRender.innerHTML = `🔗 CONNECTIONS: <span style="color: #8b949e;">NO CONNECTION</span>`;} else if (data.status === "active") { linksRender.innerHTML = `🔗 CONNECTIONS: <span class="node-active">${data.nodes.join(', ')}</span>`;} else { linksRender.innerHTML = `🔗 CONNECTIONS: <span style="color: #da3637;">OFFLINE</span>`;}}).catch(() => { linksRender.innerHTML = `🔗 CONNECTIONS: <span style="color: #da3637;">TIMEOUT</span>`;});}
const eventSource = new EventSource('/stream'); eventSource.onmessage = function(event) { if (event.data.trim() === "") return; var _ha = document.getElementById('hide-ami'); if (_ha && _ha.checked && event.data.indexOf('[AMI EVENT]') !== -1) return; const line = document.createElement('div'); line.className = 'log-line'; line.textContent = event.data; terminal.appendChild(line); terminal.scrollTop = terminal.scrollHeight;};
function triggerAction(actionName) { statusDiv.textContent = `Sending: ${actionName}...`; fetch(`/action/${actionName}`, { method: 'GET', headers: { 'X-Admin-Key': authToken}}).then(res => { if (res.status === 401) { localStorage.removeItem('node_dashboard_token'); authToken = ''; document.getElementById('pass-input').value = ''; document.getElementById('lock-overlay').style.display = 'flex'; statusDiv.textContent = '❌ Session Rejected: Unauthorized Verification Required'; throw new Error('Unauthorized');} return res.json();}).then(data => { statusDiv.textContent = data.message; setTimeout(() => { statusDiv.textContent = '';}, 4000);}).catch(err => { if (err.message !== 'Unauthorized') { statusDiv.textContent = 'Execution Error';}});}
function confirmSystemAction(actionName) { const prettyName = actionName === 'pi_reboot' ? 'REBOOT' : 'SHUTDOWN'; if (confirm(`CRITICAL WARNING: Are you sure you want to completely ${prettyName} the host Raspberry Pi hardware?`)) { triggerAction(actionName);}}
// --- DASHBOARD UPGRADE: MAP / STATUS / Q&A ---
let adsbMap = null; let adsbMarkers = {};
function initAdsbMap() { if (typeof L === 'undefined') return; if (!document.getElementById('map')) return; adsbMap = L.map('map', {maxZoom: 19}).setView([38.99, -94.76], 8); L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 12, attribution: '&copy; OpenStreetMap contributors'}).addTo(adsbMap); L.marker([38.99, -94.76]).addTo(adsbMap).bindPopup('KF0RIZ hub - Shawnee, KS'); L.circle([38.99, -94.76], {radius: 370400, color: '#58a6ff', weight: 1, fill: false, dashArray: '6 6'}).addTo(adsbMap); // Labelled places: airports, civic buildings, fire stations. var PLACES = [ {name: 'MCI', lat: 39.2982, lon: -94.71513, cls: 'ap-label'}, {name: 'New Century', lat: 38.8389, lon: -94.89602, cls: 'ap-label'}, {name: 'Olathe Exec', lat: 38.85441, lon: -94.73514, cls: 'ap-label'}, {name: 'Downtown', lat: 39.13156, lon: -94.58741, cls: 'ap-label'}, {name: "Lee's Summit", lat: 38.96205, lon: -94.37537, cls: 'ap-label'}, {name: 'Shawnee PD', lat: 39.02386, lon: -94.78227, cls: 'poi-label', ay: -22}, {name: 'Shawnee City Hall', lat: 39.0234, lon: -94.71521, cls: 'poi-label'}, {name: 'Fire 71', lat: 39.010516, lon: -94.722653, cls: 'fire-label'}, {name: 'Fire 72', lat: 39.023828, lon: -94.780433, cls: 'fire-label', ay: 14}, {name: 'Fire 73', lat: 39.00577, lon: -94.85761, cls: 'fire-label'}, {name: 'Fire 74', lat: 39.0323, lon: -94.84965, cls: 'fire-label'}]; PLACES.forEach(function(p){ var anch = (typeof p.ay === 'number') ? [0, p.ay] : [0, 0]; L.marker([p.lat, p.lon], {icon: L.divIcon({className: 'place-marker', html: '<div class="' + p.cls + '">' + p.name + '</div>', iconSize: null, iconAnchor: anch})}).addTo(adsbMap);});
var fsBtn = document.createElement('button'); fsBtn.className = 'map-fs-btn'; fsBtn.textContent = '⛶'; fsBtn.title = 'Full screen'; fsBtn.onclick = function(){ var m = document.getElementById('map'); m.classList.add('map-fullscreen'); fsBtn.style.display = 'none'; document.getElementById('map-fs-exit').classList.add('map-fs-show'); setTimeout(function(){ adsbMap.invalidateSize();}, 60);}; document.getElementById('map').appendChild(fsBtn); var fsExit = document.createElement('button'); fsExit.id = 'map-fs-exit'; fsExit.className = 'map-fs-exit'; fsExit.textContent = 'x'; fsExit.title = 'Exit full screen'; fsExit.onclick = function(){ var m = document.getElementById('map'); m.classList.remove('map-fullscreen'); fsExit.classList.remove('map-fs-show'); fsBtn.style.display = 'flex'; setTimeout(function(){ adsbMap.invalidateSize();}, 60);}; window.addEventListener('resize', function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize();}}); window.addEventListener('orientationchange', function(){ setTimeout(function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize();}}, 200);}); document.body.appendChild(fsExit);}
function fmtAlt(a) { if (a === null || a === undefined) return 'n/a'; return Math.round(a).toLocaleString() + ' ft';}
function fmtSpd(s) { if (s === null || s === undefined) return 'n/a'; return Math.round(s) + ' kt';}
function renderAircraftList(list) { const el = document.getElementById('aircraft-list'); if (!el) return; if (!list || list.length === 0) { el.innerHTML = '<div class="qa-empty">No aircraft in range.</div>'; return;} const sorted = list.slice().sort(function(x, y){ return (x.dst || 9999) - (y.dst || 9999);}); const top = sorted.slice(0, 20); let html = '<table class="ac-table"><tr><th>CALLSIGN</th><th>TYPE</th><th>ALT</th><th>SPD</th><th>DIST</th></tr>'; top.forEach(function(a){ const cls = a.priority ? ' class="ac-pri"' : ''; const dist = (a.dst !== null && a.dst !== undefined) ? Math.round(a.dst) + ' NM' : '-'; const mkey = a.reg || a.callsign; const clickable = (a.lat !== null && a.lat !== undefined && a.lon !== null && a.lon !== undefined) ? ' data-lat="' + a.lat + '" data-lon="' + a.lon + '" data-key="' + mkey + '" onclick="focusAircraft(this)" title="Tap to show on map"' : ''; html += '<tr' + cls + clickable + '><td>' + a.callsign + '</td><td>' + (a.type || '-') + '</td><td>' + fmtAlt(a.alt) + '</td><td>' + fmtSpd(a.spd) + '</td><td>' + dist + '</td></tr>';}); html += '</table>'; if (sorted.length > 20) { html += '<div class="adsb-updated">Showing nearest 20 of ' + sorted.length + ' aircraft.</div>';} el.innerHTML = html;}
function focusAircraft(row) { const lat = parseFloat(row.getAttribute('data-lat')); const lon = parseFloat(row.getAttribute('data-lon')); const key = row.getAttribute('data-key'); if (isNaN(lat) || isNaN(lon) || !adsbMap) return; adsbMap.setView([lat, lon], Math.max(adsbMap.getZoom(), 10)); if (key && adsbMarkers[key]) { adsbMarkers[key].openPopup();}}
function fmtUptime(s) { const d = Math.floor(s / 86400); const h = Math.floor((s % 86400) / 3600); const m = Math.floor((s % 3600) / 60); if (d > 0) return d + 'd ' + h + 'h'; if (h > 0) return h + 'h ' + m + 'm'; return m + 'm';}
function pollHealth() { fetch('/api/health').then(function(r){ return r.json();}).then(function(d){ const el = document.getElementById('hub-health'); if (!el) return; const temp = (d.temp_c !== null && d.temp_c !== undefined) ? d.temp_c.toFixed(1) + '°C' : '-'; const load = (d.load1 !== null && d.load1 !== undefined) ? d.load1.toFixed(2) : '-'; const up = (d.uptime_s !== null && d.uptime_s !== undefined) ? fmtUptime(d.uptime_s) : '-'; const disk = (d.disk_free_gb !== null && d.disk_free_gb !== undefined) ? Math.round(d.disk_free_gb) + ' GB free' : '-'; el.textContent = 'TEMP ' + temp + ' | LOAD ' + load + ' | UP ' + up + ' | DISK ' + disk;}).catch(function(){});}
function aircraftIcon(a) { const cat = (a.category || '').toUpperCase(); let emoji = '✈'; if (cat === 'A7') { emoji = '🚁';} else if (cat === 'A1' || cat === 'A2') { emoji = '🛩';} let rot = ''; if (emoji !== '🚁' && a.track !== null && a.track !== undefined) { rot = 'transform: rotate(' + Math.round(a.track) + 'deg);';} const halo = a.priority ? 'background: rgba(248,81,73,0.35); border-radius: 50%; padding: 2px;' : ''; return L.divIcon({ className: 'adsb-marker', html: '<span style="font-size: 22px; ' + rot + ' display: inline-block; ' + halo + '">' + emoji + '</span>', iconSize: [26, 26], iconAnchor: [13, 13]});}
function pollAircraft() { fetch('/api/aircraft').then(function(res){ return res.json();}).then(function(data){ const countEl = document.getElementById('adsb-count'); if (countEl) countEl.textContent = data.count; const nearEl = document.getElementById('adsb-nearest'); if (nearEl) nearEl.textContent = data.nearest ? (data.nearest.callsign + ' (' + Math.round(data.nearest.dst) + ' NM)') : 'none'; const priEl = document.getElementById('adsb-priority'); if (priEl) priEl.textContent = data.priority_count; const updEl = document.getElementById('adsb-updated'); if (updEl) updEl.textContent = data.updated_str ? ('Updated ' + data.updated_str) : 'Waiting for first poll...'; renderAircraftList(data.aircraft); if (!adsbMap) return; const seen = {}; data.aircraft.forEach(function(a){ const key = a.reg || a.callsign; seen[key] = true; const popup = '<b>' + a.callsign + '</b><br>' + (a.reg || '') + ' ' + (a.type || '') + '<br>Alt ' + fmtAlt(a.alt) + ' - ' + fmtSpd(a.spd) + (a.priority ? '<br><b>PRIORITY</b>' : ''); if (adsbMarkers[key]) { adsbMarkers[key].setLatLng([a.lat, a.lon]); adsbMarkers[key].setPopupContent(popup);} else { const m = L.marker([a.lat, a.lon], {icon: aircraftIcon(a)}).addTo(adsbMap); m.bindPopup(popup); adsbMarkers[key] = m;}}); Object.keys(adsbMarkers).forEach(function(k){ if (!seen[k]) { adsbMap.removeLayer(adsbMarkers[k]); delete adsbMarkers[k];}});}).catch(function(){});}
function pollRecent() { fetch('/api/recent').then(function(res){ return res.json();}).then(function(data){ const list = document.getElementById('qa-list'); if (!list) return; if (!data.items || data.items.length === 0) { list.innerHTML = '<div class="qa-empty">No questions yet in this log window.</div>'; return;} list.innerHTML = data.items.map(function(it){ return '<div class="qa-item"><div class="qa-time">' + it.time + '</div><div class="qa-q">Q: ' + it.q + '</div><div class="qa-a">A: ' + it.a + '</div></div>';}).join('');}).catch(function(){});}
function pollAiStatus() { fetch('/api/ai_status').then(function(res){ return res.json();}).then(function(data){ const s = document.getElementById('ai-status'); if (s) s.textContent = data.status; const st = document.getElementById('ai-started'); if (st) st.textContent = data.started || '-'; const lr = document.getElementById('ai-last-reply'); if (lr) lr.textContent = data.last_reply || '-'; const lk = document.getElementById('ai-last-keyup'); if (lk) lk.textContent = data.last_keyup || '-';}).catch(function(){});}
function pollPool() { fetch('/api/pool').then(function(res){ return res.json();}).then(function(data){ const k = document.getElementById('pool-key'); if (k) k.textContent = data.active_key; const c = document.getElementById('pool-calls'); if (c) c.textContent = data.recent_calls; const f = document.getElementById('pool-failover'); if (f) f.textContent = data.last_failover || 'none';}).catch(function(){});}
document.addEventListener('DOMContentLoaded', function() { initAdsbMap(); pollAircraft(); pollRecent(); pollAiStatus(); pollPool(); setInterval(pollAircraft, 30000); setInterval(pollRecent, 10000); setInterval(pollAiStatus, 10000); setInterval(pollPool, 15000); pollHealth(); setInterval(pollHealth, 30000);});
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
    m = re.search(r'\[(\d{2}:\d{2}:\d{2})', line)
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
            id_text = "This is the K F 0 R I Z... Artificial Intelligence Hub."
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
                return jsonify({"status": "success", "message": "✅ Manual Piper ID Generated & Dispatched Over-Air"})
            else:
                return jsonify({"status": "error", "message": "❌ Local Piper engine failed to output raw wave voice"})
        elif action_cmd == 'ai_start':
            subprocess.run(['sudo', 'systemctl', 'start', 'ai_orchestrator.service'], check=True)
            return jsonify({"status": "success", "message": "✅ AI Service Signal Sent: START"})
        elif action_cmd == 'ai_stop':
            subprocess.run(['sudo', 'systemctl', 'stop', 'ai_orchestrator.service'], check=True)
            return jsonify({"status": "success", "message": "🛑 AI Service Signal Sent: STOP"})
        elif action_cmd == 'ai_restart':
            subprocess.run(['sudo', 'systemctl', 'restart', 'ai_orchestrator.service'], check=True)
            return jsonify({"status": "success", "message": "🔄 AI Service Cycle Initiated"})
        elif action_cmd == 'pi_reboot':
            subprocess.Popen(['sudo', 'systemctl', 'reboot'])
            return jsonify({"status": "success", "message": "🌀 Hardware Reboot Command Dispatched..."})
        elif action_cmd == 'pi_shutdown':
            subprocess.Popen(['sudo', 'systemctl', 'poweroff'])
            return jsonify({"status": "success", "message": "🔌 Hardware Poweroff Dispatched..."})
        return jsonify({"status": "unknown", "message": "⚠ Unrecognized command parameter"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"❌ Execution Failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=62573, debug=False)
