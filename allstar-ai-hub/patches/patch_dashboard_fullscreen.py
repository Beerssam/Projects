#!/usr/bin/env python3
"""Dashboard: fullscreen map button, deeper zoom, and un-overlapped labels.
- Lets the map zoom in to 19 (OpenStreetMap max) so you can zoom right in.
- Adds a fullscreen button in the bottom-right corner of the map. Tap it and
  the map fills the whole screen; an exit button appears in the top-right to
  go back to the dashboard.
- Staggers the two labels that sit on top of each other (Fire 72 and Shawnee
  PD are ~10 m apart on Renner Rd) so they no longer overlap.
Target: /home/asl/ai_dashboard.py with the zoom+places patch applied
(zoom 8, PLACES array, ap/poi/fire label CSS).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import re
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_fullscreen_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("Map maxZoom 19",
     "adsbMap = L.map('map').setView([38.99, -94.76], 8);",
     "adsbMap = L.map('map', {maxZoom: 19}).setView([38.99, -94.76], 8);"),
    ("CSS: fullscreen map + buttons",
     ".fire-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #f85149; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap; }",
     ".fire-label { background: rgba(13,17,23,0.88); color: #e6edf3; border: 1px solid #f85149; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; white-space: nowrap; }\n.map-fullscreen { position: fixed !important; top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important; width: 100vw !important; height: 100vh !important; height: 100dvh !important; z-index: 1000 !important; border-radius: 0 !important; margin: 0 !important; }\n.map-fs-btn { position: absolute; right: 10px; bottom: 24px; z-index: 1001; background: rgba(13,17,23,0.92); color: #e6edf3; border: 1px solid #58a6ff; border-radius: 6px; padding: 8px 12px; font-size: 13px; font-weight: 700; cursor: pointer; }\n.map-fs-exit { position: fixed; right: 12px; top: 12px; z-index: 1002; background: rgba(13,17,23,0.92); color: #e6edf3; border: 1px solid #f85149; border-radius: 6px; padding: 8px 12px; font-size: 13px; font-weight: 700; cursor: pointer; display: none; }"),
    ("Stagger Fire 72 / PD labels (same spot on Renner Rd)",
     "{name: 'Shawnee PD', lat: 39.02386, lon: -94.78227, cls: 'poi-label'},",
     "{name: 'Shawnee PD', lat: 39.02386, lon: -94.78227, cls: 'poi-label', ay: -22},"),
    ("Stagger Fire 72 label down",
     "{name: 'Fire 72', lat: 39.023828, lon: -94.780433, cls: 'fire-label'},",
     "{name: 'Fire 72', lat: 39.023828, lon: -94.780433, cls: 'fire-label', ay: 14},"),
    ("JS: fullscreen toggle + label anchor",
     "PLACES.forEach(function(p){ L.marker([p.lat, p.lon], {icon: L.divIcon({className: 'place-marker', html: '<div class=\"' + p.cls + '\">' + p.name + '</div>', iconSize: null})}).addTo(adsbMap); });",
     "PLACES.forEach(function(p){ var anch = (typeof p.ay === 'number') ? [0, p.ay] : [0, 0]; L.marker([p.lat, p.lon], {icon: L.divIcon({className: 'place-marker', html: '<div class=\"' + p.cls + '\">' + p.name + '</div>', iconSize: null, iconAnchor: anch})}).addTo(adsbMap); });\n    // Fullscreen map toggle (button bottom-right, exit top-right).\n    var fsBtn = document.createElement('button');\n    fsBtn.className = 'map-fs-btn'; fsBtn.textContent = '⛶ Full screen';\n    fsBtn.onclick = function(){ var m = document.getElementById('map'); m.classList.add('map-fullscreen'); document.getElementById('map-fs-exit').style.display = 'block'; setTimeout(function(){ adsbMap.invalidateSize(); }, 50); };\n    document.getElementById('map').appendChild(fsBtn);\n    var fsExit = document.createElement('button');\n    fsExit.id = 'map-fs-exit'; fsExit.className = 'map-fs-exit'; fsExit.textContent = '✕ Exit full screen';\n    fsExit.onclick = function(){ var m = document.getElementById('map'); m.classList.remove('map-fullscreen'); fsExit.style.display = 'none'; setTimeout(function(){ adsbMap.invalidateSize(); }, 50); };\n    document.body.appendChild(fsExit);"),
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
