#!/usr/bin/env python3
"""patch_dashboard_cascade4.py - AI Hub dashboard: corner toggle switch
(Nov 25 2026)

Replaces the big "Web Search" button from cascade3 with a small toggle
switch in the top-right corner of the GEMINI POOL panel title (Sam's
request: discreet, off to the side).

It also fixes the real usability bug Sam hit: the old button's enabled
state was only refreshed by the 15-second pool poll, so right after
unlocking it sat grayed out until a poll happened to land. The switch
is now painted by a single helper, syncSearchSwitch(), which is called
from FOUR places:
  - pollPool (every poll, as before),
  - unlockControls (the moment the password is entered),
  - DOMContentLoaded when a cached token auto-unlocks the page,
  - triggerAction's 401 branch (a rejected session grays it at once).
The switch position/color always reflect the server-reported state:
knob right + green = search ON, knob left + gray = OFF; dimmed and
disabled while the console is locked.

Safety: every anchor must match exactly once or the patch aborts with
no changes. The new source is compiled in memory BEFORE writing; a
timestamped backup is taken; result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade4.py
Then:      sudo systemctl restart ai_dashboard
Rollback: copy the backup back over ai_dashboard.py and restart.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_dashboard.py"

with open(PATH) as f:
    src = f.read()

# --- Edit 1: the switch itself, floated into the panel title's corner ---
old_title = """    <div class="panel-title">GEMINI POOL</div>"""
new_title = """    <div class="panel-title">GEMINI POOL <span style="float:right; font-size:11px;">WEB SEARCH <button id="search-toggle" onclick="toggleSearch()" disabled title="Toggle web search" style="width:40px; height:20px; border-radius:10px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="search-knob" style="position:absolute; top:2px; left:2px; width:16px; height:16px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button></span></div>"""

# --- Edit 2: remove the old full-width button ---
old_btn = """    <div style="margin-top:8px;"><button id="search-toggle" onclick="toggleSearch()" disabled style="opacity:0.45;">&#128269; Web Search: ...</button></div>
"""
new_btn = ""

# --- Edit 3: pollPool delegates painting to the helper ---
old_tb = """        const tb = document.getElementById('search-toggle');
        if (tb) {
            window._searchEnabled = (data.search_enabled !== false);
            if (typeof authToken !== 'undefined' && authToken) {
                tb.disabled = false;
                tb.style.opacity = '1';
            } else {
                tb.disabled = true;
                tb.style.opacity = '0.45';
            }
            tb.textContent = window._searchEnabled ? '🔍 Web Search: ON - tap to turn OFF' : '🔍 Web Search: OFF - tap to turn ON';
        }"""
new_tb = """        window._searchEnabled = (data.search_enabled !== false);
        syncSearchSwitch();"""

# --- Edit 4: the helper, inserted just before toggleSearch ---
old_tog = """function toggleSearch() {"""
new_tog = """function syncSearchSwitch() {
    const tb = document.getElementById('search-toggle');
    if (!tb) return;
    const on = window._searchEnabled !== false;
    const kn = document.getElementById('search-knob');
    if (kn) kn.style.left = on ? '22px' : '2px';
    tb.style.background = on ? '#238636' : '#484f58';
    if (typeof authToken !== 'undefined' && authToken) {
        tb.disabled = false;
        tb.style.opacity = '1';
    } else {
        tb.disabled = true;
        tb.style.opacity = '0.45';
    }
}
function toggleSearch() {"""

# --- Edit 5: unlock wakes the switch immediately ---
old_unlock = """            authToken = passValue;
            localStorage.setItem('node_dashboard_token', passValue);
            document.getElementById('lock-overlay').style.display = 'none';
        }"""
new_unlock = """            authToken = passValue;
            localStorage.setItem('node_dashboard_token', passValue);
            document.getElementById('lock-overlay').style.display = 'none';
            syncSearchSwitch();
        }"""

# --- Edit 6: a cached token (auto-unlock on load) wakes it too ---
old_ready = """            if (authToken) {
                document.getElementById('lock-overlay').style.display = 'none';
            }"""
new_ready = """            if (authToken) {
                document.getElementById('lock-overlay').style.display = 'none';
                syncSearchSwitch();
            }"""

# --- Edit 7: a rejected session grays it again at once ---
old_401 = """                    localStorage.removeItem('node_dashboard_token');
                    authToken = '';"""
new_401 = """                    localStorage.removeItem('node_dashboard_token');
                    authToken = '';
                    syncSearchSwitch();"""

EDITS = [
    ("title", old_title, new_title),
    ("btn", old_btn, new_btn),
    ("tb", old_tb, new_tb),
    ("tog", old_tog, new_tog),
    ("unlock", old_unlock, new_unlock),
    ("ready", old_ready, new_ready),
    ("401", old_401, new_401),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade4"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_dashboard")
