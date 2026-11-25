#!/usr/bin/env python3
"""patch_dashboard_cascade3.py - AI dashboard panel v3 (Nov 25 2026)

On top of patch_dashboard_cascade.py + patch_dashboard_cascade2.py:

1. LAYOUT: each cascade model gets its own two-line block (name + status
   badge on one line, used/left numbers on the next) so nothing wraps
   mid-phrase on a phone screen.
2. SEARCH LINE: always shows the real state -
   ON with the count of Google searches completed today;
   GOOGLE SPENT with the search count and how many times the DuckDuckGo
   backup was used today; or OFF (manual).
3. TOGGLE BUTTON: in the GEMINI POOL panel, flips web search on/off via
   two new dashboard actions (search_on / search_off) that write
   /home/asl/ai_search_control.json. The actions ride the existing
   /action auth (X-Admin-Key header vs the dashboard password), and the
   button stays disabled and dimmed until the console is unlocked with
   the control key - the same unlock as the other controls.

Safety: every anchor must match exactly once or the patch aborts with no
changes. A timestamped backup is written first; result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade3.py
Then:      sudo systemctl restart ai_dashboard
Rollback: copy the backup back over ai_dashboard.py and restart it.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_dashboard.py"

with open(PATH) as f:
    src = f.read()

# --- Edit 1: HTML - the toggle button under the search line ---
old_html = """    <div id="pool-cascade" style="margin-top:6px;"></div>
    <div class="stat-line" id="pool-grounding"></div>
</div>"""
new_html = """    <div id="pool-cascade" style="margin-top:6px;"></div>
    <div class="stat-line" id="pool-grounding"></div>
    <div style="margin-top:8px;"><button id="search-toggle" onclick="toggleSearch()" disabled style="opacity:0.45;">&#128269; Web Search: ...</button></div>
</div>"""

# --- Edit 2: JS - per-model two-line blocks (no mid-phrase wrapping) ---
old_render = """                data.cascade.forEach(function(m){
                    var name = m.model.replace('gemini-', '');
                    var status = m.exhausted ? ' <span style="color:#f85149;">SPENT</span>' : (m.current ? ' <span style="color:#3fb950;">ACTIVE</span>' : (m.next ? ' <span style="color:#e3b341;">NEXT</span>' : ''));
                    html += '<div class="stat-line">' + name + ': <b>' + m.used + ' used, ~' + m.left + ' left</b> / ' + m.cap + status + '</div>';
                });
                html += '<div class="stat-line">QUESTIONS TODAY: <b>' + (data.total_answered || 0) + '</b></div>';"""
new_render = """                data.cascade.forEach(function(m){
                    var name = m.model.replace('gemini-', '');
                    var status = m.exhausted ? '<span style="color:#f85149;">SPENT</span>' : (m.current ? '<span style="color:#3fb950;">ACTIVE</span>' : (m.next ? '<span style="color:#e3b341;">NEXT</span>' : ''));
                    html += '<div style="margin:7px 0;"><div><b>' + name + '</b> ' + status + '</div><div class="stat-line">' + m.used + ' used &middot; ~' + m.left + ' left of ' + m.cap + '</div></div>';
                });
                html += '<div class="stat-line" style="margin-top:7px;">QUESTIONS TODAY: <b>' + (data.total_answered || 0) + '</b></div>';"""

# --- Edit 3: JS - the search line + toggle button state ---
old_ground = """        const gr = document.getElementById('pool-grounding');
        if (gr) gr.textContent = (data.cascade && data.cascade.length) ? (data.grounding_dead ? 'WEB SEARCH: OFF (spent for today - answers continue without it)' : 'WEB SEARCH: ON') : '';"""
new_ground = """        const gr = document.getElementById('pool-grounding');
        if (gr) {
            if (!data.cascade || !data.cascade.length) {
                gr.textContent = '';
            } else if (data.search_enabled === false) {
                gr.textContent = 'WEB SEARCH: OFF (manual) · ' + (data.searches || 0) + ' searches today';
            } else if (data.grounding_dead) {
                gr.textContent = 'WEB SEARCH: GOOGLE SPENT · ' + (data.searches || 0) + ' searches today · DDG backup used ' + (data.ddg_searches || 0) + 'x';
            } else {
                gr.textContent = 'WEB SEARCH: ON · ' + (data.searches || 0) + ' searches today';
            }
        }
        const tb = document.getElementById('search-toggle');
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

# --- Edit 4: JS - the toggle handler, before colorBand ---
old_color = """function colorBand(v) {"""
new_color = """function toggleSearch() {
    if (typeof authToken === 'undefined' || !authToken) return;
    triggerAction(window._searchEnabled ? 'search_off' : 'search_on');
    setTimeout(pollPool, 900);
}
function colorBand(v) {"""

# --- Edit 5: /api/pool - search counters + manual switch state ---
old_api = """    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover, "cascade": cascade, "grounding_dead": grounding_dead, "quota_day": quota_day, "total_answered": total_answered})"""
new_api = """    searches = 0
    ddg_searches = 0
    try:
        searches = _st.get("searches", 0)
        ddg_searches = _st.get("ddg_searches", 0)
    except Exception:
        pass
    search_enabled = True
    try:
        import json as _json2
        with open("/home/asl/ai_search_control.json") as _cf:
            search_enabled = bool(_json2.load(_cf).get("enabled", True))
    except Exception:
        search_enabled = True
    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover, "cascade": cascade, "grounding_dead": grounding_dead, "quota_day": quota_day, "total_answered": total_answered, "searches": searches, "ddg_searches": ddg_searches, "search_enabled": search_enabled})"""

# --- Edit 6: /action - search_on / search_off (existing auth applies) ---
old_action = """        elif action_cmd == 'pi_shutdown':
            subprocess.Popen(['sudo', 'systemctl', 'poweroff'])
            return jsonify({"status": "success", "message": "🔌 Hardware Poweroff Command Dispatched..."})"""
new_action = """        elif action_cmd == 'pi_shutdown':
            subprocess.Popen(['sudo', 'systemctl', 'poweroff'])
            return jsonify({"status": "success", "message": "🔌 Hardware Poweroff Command Dispatched..."})
        elif action_cmd == 'search_on':
            with open("/home/asl/ai_search_control.json", "w") as _cf:
                json.dump({"enabled": True}, _cf)
            return jsonify({"status": "success", "message": "🔍 Web Search: ON"})
        elif action_cmd == 'search_off':
            with open("/home/asl/ai_search_control.json", "w") as _cf:
                json.dump({"enabled": False}, _cf)
            return jsonify({"status": "success", "message": "🔍 Web Search: OFF (hub answers without web search)"})"""

EDITS = [
    ("html", old_html, new_html),
    ("render", old_render, new_render),
    ("ground", old_ground, new_ground),
    ("color", old_color, new_color),
    ("api", old_api, new_api),
    ("action", old_action, new_action),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade3"
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
