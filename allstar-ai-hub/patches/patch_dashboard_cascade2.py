#!/usr/bin/env python3
"""patch_dashboard_cascade2.py - AI dashboard: cascade panel v2 (Nov 25 2026)

Follow-up to patch_dashboard_cascade.py (must be applied first), per Sam's
review of the panel. Adds, inside the existing GEMINI POOL panel:

- a NEXT marker on the model that takes over when the current one is spent
- a QUESTIONS TODAY line: total questions answered today, all models
- the WEB SEARCH line now always shows its state: ON, or OFF when the
  day's grounding allowance is spent (answers continue without it)

Nothing else changes. Safety: every anchor must match exactly once or the
patch aborts with no changes. A timestamped backup is written first; the
result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade2.py
Then restart the dashboard service.
Rollback: copy the backup back over ai_dashboard.py and restart it.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_dashboard.py"

with open(PATH) as f:
    src = f.read()

# --- Edit 1: /api/pool - compute total answered + the NEXT model ---
old_api = """    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover, "cascade": cascade, "grounding_dead": grounding_dead, "quota_day": quota_day})"""
new_api = """    total_answered = 0
    try:
        total_answered = sum(_e.get("answered", 0) for _e in _st.get("models", {}).values())
    except Exception:
        total_answered = 0
    _seen_current = False
    _next_done = False
    for _row in cascade:
        _row["next"] = False
        if _row["current"]:
            _seen_current = True
            continue
        if not _row["exhausted"] and (_seen_current or not _cur) and not _next_done:
            _row["next"] = True
            _next_done = True
    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover, "cascade": cascade, "grounding_dead": grounding_dead, "quota_day": quota_day, "total_answered": total_answered})"""

# --- Edit 2: pollPool JS - NEXT marker + QUESTIONS TODAY row ---
old_js = """                data.cascade.forEach(function(m){
                    var name = m.model.replace('gemini-', '');
                    var status = m.exhausted ? ' <span style="color:#f85149;">SPENT</span>' : (m.current ? ' <span style="color:#3fb950;">ACTIVE</span>' : '');
                    html += '<div class="stat-line">' + name + ': <b>' + m.used + ' used, ~' + m.left + ' left</b> / ' + m.cap + status + '</div>';
                });"""
new_js = """                data.cascade.forEach(function(m){
                    var name = m.model.replace('gemini-', '');
                    var status = m.exhausted ? ' <span style="color:#f85149;">SPENT</span>' : (m.current ? ' <span style="color:#3fb950;">ACTIVE</span>' : (m.next ? ' <span style="color:#e3b341;">NEXT</span>' : ''));
                    html += '<div class="stat-line">' + name + ': <b>' + m.used + ' used, ~' + m.left + ' left</b> / ' + m.cap + status + '</div>';
                });
                html += '<div class="stat-line">QUESTIONS TODAY: <b>' + (data.total_answered || 0) + '</b></div>';"""

# --- Edit 3: pollPool JS - WEB SEARCH always shows ON/OFF ---
old_gr = """        if (gr) gr.textContent = data.grounding_dead ? 'WEB SEARCH: spent for today - answers continue without it' : '';"""
new_gr = """        if (gr) gr.textContent = (data.cascade && data.cascade.length) ? (data.grounding_dead ? 'WEB SEARCH: OFF (spent for today - answers continue without it)' : 'WEB SEARCH: ON') : '';"""

EDITS = [
    ("api", old_api, new_api),
    ("js", old_js, new_js),
    ("grounding", old_gr, new_gr),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade2"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart the dashboard service.")
