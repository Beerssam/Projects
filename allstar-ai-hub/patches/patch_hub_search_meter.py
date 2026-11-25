#!/usr/bin/env python3
"""patch_hub_search_meter.py - AllStar AI Hub: search meter + manual switch
(Nov 25 2026)

Two additions to ai_orchestrator.py, on top of the cascade patch:

1. SEARCH METER: the state file gains "searches" - the number of search
   (grounded) requests Google accepted today. The dashboard shows it next
   to WEB SEARCH: ON/OFF. (Google does not publish the free grounding
   allowance, so there is no honest "searches left" number; the count of
   completed searches plus the ON/OFF state is what can be shown.)

2. MANUAL SEARCH SWITCH: if /home/asl/ai_search_control.json exists with
   {"enabled": false}, the hub skips search entirely (every question goes
   straight to the ungrounded route) until the file says true again. The
   dashboard's toggle button writes this file. Missing or unreadable file
   = search enabled (fail-open). The daily grounding allowance logic is
   unchanged: spent-for-the-day still flips to ungrounded automatically.

Safety: every anchor must match exactly once or the patch aborts with no
changes. A timestamped backup is written first; result must py_compile.

Run with:  sudo python3 patch_hub_search_meter.py
Then:      sudo systemctl restart ai_orchestrator
Rollback: copy the backup back over ai_orchestrator.py and restart.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_orchestrator.py"

with open(PATH) as f:
    src = f.read()

# --- Edit 1: state gains a "searches" counter, defaulting to 0 ---
old_state = """        _st = {"day": _day, "grounding_dead": False, "current_model": "", "models": {}}"""
new_state = """        _st = {"day": _day, "grounding_dead": False, "current_model": "", "models": {}}
    _st.setdefault("searches", 0)"""

# --- Edit 2: the manual switch gates the grounded routes ---
old_routes = """    for _m, _c in _models:
        if not _state.get("grounding_dead"):
            _routes.append((_m, payload))"""
new_routes = """    _search_on = True
    try:
        with open("/home/asl/ai_search_control.json") as _cf:
            _search_on = bool(json.load(_cf).get("enabled", True))
    except Exception:
        _search_on = True
    for _m, _c in _models:
        if _search_on and not _state.get("grounding_dead"):
            _routes.append((_m, payload))"""

# --- Edit 3: count each accepted search request ---
old_book = """            _state["current_model"] = _model
            _state["models"][_model]["answered"] = _state["models"][_model].get("answered", 0) + 1
            _save_state(_state)"""
new_book = """            _state["current_model"] = _model
            _state["models"][_model]["answered"] = _state["models"][_model].get("answered", 0) + 1
            _save_state(_state)
            if _pl is payload:
                _state["searches"] = _state.get("searches", 0) + 1
                _save_state(_state)"""

EDITS = [
    ("state", old_state, new_state),
    ("routes", old_routes, new_routes),
    ("book", old_book, new_book),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searchmeter"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
