#!/usr/bin/env python3
"""patch_dashboard_cascade5.py - AI Hub dashboard: engine switches +
sticky LAST REPLY / LAST KEY-UP (Nov 25 2026)

Two changes:

1) ENGINE SWITCHES. Two mini toggle switches join the master WEB SEARCH
   switch in the GEMINI POOL panel: GOOGLE and DUCKDUCKGO. The control
   file gains "google" and "ddg" flags next to "enabled". Write rules
   (Sam's spec):
   - Master OFF turns both engines off too.
   - Turning both engines off turns the master off.
   - Master ON turns both engines on (the autonomous default).
   - An engine ON also turns the master on.
   With everything on, behavior is exactly as before: Google first,
   DDG backup when Google is spent. Google OFF alone = DDG-only mode
   for testing; DDG OFF alone = Google-only, no fallover.
   /api/pool reports search_google / search_ddg so the switches always
   paint the server's real state; the status line gains a DDG ONLY
   variant.

2) STICKY LAST REPLY / LAST KEY-UP. ai_status scraped the last 300 log
   lines; the AMI chatter pushes the markers out within minutes, so
   both readouts sat blank. The route now remembers the newest values
   it has seen (module-level dict) and seeds them once from a deep
   20,000-line scan after a dashboard restart.

Safety: every anchor must match exactly once or the patch aborts with
no changes. The new source is compiled in memory BEFORE writing; a
timestamped backup is taken; result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade5.py
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

# --- Edit 1: /api/pool reports the engine flags ---
old_api = """    search_enabled = True
    try:
        import json as _json2
        with open("/home/asl/ai_search_control.json") as _cf:
            search_enabled = bool(_json2.load(_cf).get("enabled", True))
    except Exception:
        search_enabled = True
    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover, "cascade": cascade, "grounding_dead": grounding_dead, "quota_day": quota_day, "total_answered": total_answered, "searches": searches, "ddg_searches": ddg_searches, "search_enabled": search_enabled})"""
new_api = """    search_enabled = True
    search_google = True
    search_ddg = True
    try:
        import json as _json2
        with open("/home/asl/ai_search_control.json") as _cf:
            _ctl = _json2.load(_cf)
        search_enabled = bool(_ctl.get("enabled", True))
        search_google = bool(_ctl.get("google", True))
        search_ddg = bool(_ctl.get("ddg", True))
    except Exception:
        pass
    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover, "cascade": cascade, "grounding_dead": grounding_dead, "quota_day": quota_day, "total_answered": total_answered, "searches": searches, "ddg_searches": ddg_searches, "search_enabled": search_enabled, "search_google": search_google, "search_ddg": search_ddg})"""

# --- Edit 2: one settings action with the master/engine write rules ---
old_action = """        elif action_cmd == 'search_on':
            with open("/home/asl/ai_search_control.json", "w") as _cf:
                json.dump({"enabled": True}, _cf)
            return jsonify({"status": "success", "message": "🔍 Web Search: ON"})
        elif action_cmd == 'search_off':
            with open("/home/asl/ai_search_control.json", "w") as _cf:
                json.dump({"enabled": False}, _cf)
            return jsonify({"status": "success", "message": "🔍 Web Search: OFF (hub answers without web search)"})"""
new_action = """        elif action_cmd in ('search_on', 'search_off', 'google_on', 'google_off', 'ddg_on', 'ddg_off'):
            _ctl = {"enabled": True, "google": True, "ddg": True}
            try:
                with open("/home/asl/ai_search_control.json") as _cf:
                    _saved = json.load(_cf)
                for _k in _ctl:
                    if _k in _saved:
                        _ctl[_k] = bool(_saved[_k])
            except Exception:
                pass
            if action_cmd == 'search_on':
                _ctl.update({"enabled": True, "google": True, "ddg": True})
            elif action_cmd == 'search_off':
                _ctl.update({"enabled": False, "google": False, "ddg": False})
            elif action_cmd == 'google_on':
                _ctl.update({"google": True, "enabled": True})
            elif action_cmd == 'google_off':
                _ctl["google"] = False
                _ctl["enabled"] = bool(_ctl["google"] or _ctl["ddg"])
            elif action_cmd == 'ddg_on':
                _ctl.update({"ddg": True, "enabled": True})
            elif action_cmd == 'ddg_off':
                _ctl["ddg"] = False
                _ctl["enabled"] = bool(_ctl["google"] or _ctl["ddg"])
            with open("/home/asl/ai_search_control.json", "w") as _cf:
                json.dump(_ctl, _cf)
            return jsonify({"status": "success", "message": "🔍 Search: master " + ("ON" if _ctl["enabled"] else "OFF") + ", Google " + ("ON" if _ctl["google"] else "OFF") + ", DDG " + ("ON" if _ctl["ddg"] else "OFF")})"""

# --- Edit 3: the two mini switches under the status line ---
old_html = """    <div class="stat-line" id="pool-grounding"></div>"""
new_html = """    <div class="stat-line" id="pool-grounding"></div>
    <div class="stat-line" style="margin-top:6px;">GOOGLE <button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style="width:34px; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="google-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button> &nbsp; DUCKDUCKGO <button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style="width:34px; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="ddg-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button></div>"""

# --- Edit 4: the status line learns the DDG ONLY state ---
old_gr = """            } else {
                gr.textContent = 'WEB SEARCH: ON · ' + (data.searches || 0) + ' searches today';
            }"""
new_gr = """            } else if (data.search_google === false) {
                gr.textContent = 'WEB SEARCH: DDG ONLY (Google off) · ' + (data.ddg_searches || 0) + ' DDG searches today';
            } else {
                gr.textContent = 'WEB SEARCH: ON · ' + (data.searches || 0) + ' searches today';
            }"""

# --- Edit 5: pollPool picks up the engine flags too ---
old_tb = """        window._searchEnabled = (data.search_enabled !== false);
        syncSearchSwitch();"""
new_tb = """        window._searchEnabled = (data.search_enabled !== false);
        window._googleEnabled = (data.search_google !== false);
        window._ddgEnabled = (data.search_ddg !== false);
        syncSearchSwitch();"""

# --- Edit 6: the painter now handles all three switches ---
old_sync = """function syncSearchSwitch() {
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
}"""
new_sync = """function syncSearchSwitch() {
    const unlocked = (typeof authToken !== 'undefined' && authToken);
    const paint = function(btnId, knobId, isOn, travel) {
        const b = document.getElementById(btnId);
        if (!b) return;
        const k = document.getElementById(knobId);
        if (k) k.style.left = isOn ? travel : '2px';
        b.style.background = isOn ? '#238636' : '#484f58';
        b.disabled = !unlocked;
        b.style.opacity = unlocked ? '1' : '0.45';
    };
    paint('search-toggle', 'search-knob', window._searchEnabled !== false, '22px');
    paint('google-toggle', 'google-knob', window._googleEnabled !== false, '18px');
    paint('ddg-toggle', 'ddg-knob', window._ddgEnabled !== false, '18px');
}"""

# --- Edit 7: click handlers for the engine switches ---
old_tog = """function toggleSearch() {
    if (typeof authToken === 'undefined' || !authToken) return;
    triggerAction(window._searchEnabled ? 'search_off' : 'search_on');
    setTimeout(pollPool, 900);
}"""
new_tog = """function toggleSearch() {
    if (typeof authToken === 'undefined' || !authToken) return;
    triggerAction(window._searchEnabled ? 'search_off' : 'search_on');
    setTimeout(pollPool, 900);
}
function toggleGoogle() {
    if (typeof authToken === 'undefined' || !authToken) return;
    triggerAction(window._googleEnabled ? 'google_off' : 'google_on');
    setTimeout(pollPool, 900);
}
function toggleDdg() {
    if (typeof authToken === 'undefined' || !authToken) return;
    triggerAction(window._ddgEnabled ? 'ddg_off' : 'ddg_on');
    setTimeout(pollPool, 900);
}"""

# --- Edit 8: sticky storage for ai_status ---
old_route = """@app.route('/api/ai_status')
def ai_status_api():"""
new_route = """_sticky_status = {"last_reply": "", "last_keyup": ""}


@app.route('/api/ai_status')
def ai_status_api():"""

# --- Edit 9: sticky LAST REPLY / LAST KEY-UP ---
old_status = """    last_reply = ""
    for line in reversed(_tail_log(300)):
        if "[GEMINI RESPONSE]" in line:
            last_reply = _log_time(line)
            break
    last_keyup = ""
    for line in reversed(_tail_log(300)):
        if "[WHISPER GATE]" in line or "[RADIO INTERPRETATION]" in line:
            last_keyup = _log_time(line)
            break
    return jsonify({"status": status, "started": started, "last_reply": last_reply, "last_keyup": last_keyup})"""
new_status = """    # Sticky values: the markers scroll out of the 300-line tail within
    # minutes under AMI chatter, so remember the newest seen and seed
    # once from a deep scan after a dashboard restart. Times are parsed
    # inline here: the log's timestamp gained a date on Nov 24, which
    # the shared _log_time pattern (bracket-anchored) no longer matches,
    # so the readouts were blank even when a marker was in the tail.
    def _t_of(_line):
        _m = re.search(r"(\\d{2}:\\d{2}:\\d{2})", _line)
        return _m.group(1) if _m else ""
    if not _sticky_status["last_reply"] or not _sticky_status["last_keyup"]:
        for line in reversed(_tail_log(20000)):
            if not _sticky_status["last_reply"] and "[GEMINI RESPONSE]" in line:
                _sticky_status["last_reply"] = _t_of(line)
            if not _sticky_status["last_keyup"] and ("[WHISPER GATE]" in line or "[RADIO INTERPRETATION]" in line):
                _sticky_status["last_keyup"] = _t_of(line)
            if _sticky_status["last_reply"] and _sticky_status["last_keyup"]:
                break
    for line in reversed(_tail_log(300)):
        if "[GEMINI RESPONSE]" in line:
            _t = _t_of(line)
            if _t:
                _sticky_status["last_reply"] = _t
            break
    for line in reversed(_tail_log(300)):
        if "[WHISPER GATE]" in line or "[RADIO INTERPRETATION]" in line:
            _t = _t_of(line)
            if _t:
                _sticky_status["last_keyup"] = _t
            break
    return jsonify({"status": status, "started": started, "last_reply": _sticky_status["last_reply"], "last_keyup": _sticky_status["last_keyup"]})"""

EDITS = [
    ("api", old_api, new_api),
    ("action", old_action, new_action),
    ("html", old_html, new_html),
    ("gr", old_gr, new_gr),
    ("tb", old_tb, new_tb),
    ("sync", old_sync, new_sync),
    ("tog", old_tog, new_tog),
    ("route", old_route, new_route),
    ("status", old_status, new_status),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade5"
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
