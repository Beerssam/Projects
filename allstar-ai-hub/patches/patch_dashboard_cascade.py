#!/usr/bin/env python3
"""patch_dashboard_cascade.py - AI dashboard: show the model cascade (Nov 25 2026)

Extends the GEMINI POOL panel of /home/asl/ai_dashboard.py with the cascade
state written by the orchestrator (patch_hub_cascade.py) to
/home/asl/ai_model_state.json:

- one line per model, in cascade order: requests used today, estimated
  left, and the model's daily cap
- the currently answering model marked ACTIVE, a spent model marked SPENT
- a note when web search grounding is spent for the day

The existing ACTIVE KEY / RECENT REPLIES / LAST FAILOVER lines are
unchanged; /api/pool keeps its current fields and gains "cascade",
"grounding_dead" and "quota_day". If the state file does not exist yet,
the panel shows "CASCADE: no data yet" and nothing breaks.

Safety: every anchor must match exactly once or the patch aborts with no
changes. A timestamped backup is written first; result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade.py
Then restart the dashboard service (check its unit name first if unsure:
systemctl list-units | grep -i dash).
Rollback: copy the backup back over ai_dashboard.py and restart it.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_dashboard.py"

with open(PATH) as f:
    src = f.read()

# --- Edit 1: panel HTML - add the cascade container under LAST FAILOVER ---
old_html = """    <div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div>
</div>"""
new_html = """    <div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div>
    <div id="pool-cascade" style="margin-top:6px;"></div>
    <div class="stat-line" id="pool-grounding"></div>
</div>"""

# --- Edit 2: pollPool JS - render the cascade rows ---
old_js = """function pollPool() {
    fetch('/api/pool').then(function(res){ return res.json(); }).then(function(data){
        const k = document.getElementById('pool-key');
        if (k) k.textContent = data.active_key;
        const c = document.getElementById('pool-calls');
        if (c) c.textContent = data.recent_calls;
        const f = document.getElementById('pool-failover');
        if (f) f.textContent = data.last_failover || 'none';
    }).catch(function(){});
}"""
new_js = """function pollPool() {
    fetch('/api/pool').then(function(res){ return res.json(); }).then(function(data){
        const k = document.getElementById('pool-key');
        if (k) k.textContent = data.active_key;
        const c = document.getElementById('pool-calls');
        if (c) c.textContent = data.recent_calls;
        const f = document.getElementById('pool-failover');
        if (f) f.textContent = data.last_failover || 'none';
        const cz = document.getElementById('pool-cascade');
        if (cz) {
            if (data.cascade && data.cascade.length) {
                var html = '';
                data.cascade.forEach(function(m){
                    var name = m.model.replace('gemini-', '');
                    var status = m.exhausted ? ' <span style="color:#f85149;">SPENT</span>' : (m.current ? ' <span style="color:#3fb950;">ACTIVE</span>' : '');
                    html += '<div class="stat-line">' + name + ': <b>' + m.used + ' used, ~' + m.left + ' left</b> / ' + m.cap + status + '</div>';
                });
                cz.innerHTML = html;
            } else {
                cz.innerHTML = '<div class="stat-line">CASCADE: no data yet</div>';
            }
        }
        const gr = document.getElementById('pool-grounding');
        if (gr) gr.textContent = data.grounding_dead ? 'WEB SEARCH: spent for today - answers continue without it' : '';
    }).catch(function(){});
}"""

# --- Edit 3: /api/pool - add the cascade state to the JSON ---
old_api = """    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover})"""
new_api = """    cascade = []
    grounding_dead = False
    quota_day = ""
    try:
        import json as _json
        with open("/home/asl/ai_model_state.json") as _sf:
            _st = _json.load(_sf)
        quota_day = _st.get("day", "")
        grounding_dead = bool(_st.get("grounding_dead"))
        _cur = _st.get("current_model", "")
        for _m, _e in _st.get("models", {}).items():
            _cap = _e.get("cap", 0)
            _used = _e.get("used", 0)
            cascade.append({"model": _m, "used": _used, "cap": _cap,
                            "left": max(0, _cap - _used),
                            "exhausted": bool(_e.get("exhausted")),
                            "current": (_m == _cur)})
    except Exception:
        cascade = []
    return jsonify({"active_key": active_key, "recent_calls": recent_calls, "last_failover": last_failover, "cascade": cascade, "grounding_dead": grounding_dead, "quota_day": quota_day})"""

EDITS = [
    ("html", old_html, new_html),
    ("js", old_js, new_js),
    ("api", old_api, new_api),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart the dashboard service.")
