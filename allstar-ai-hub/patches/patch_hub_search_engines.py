#!/usr/bin/env python3
"""patch_hub_search_engines.py - AllStar AI Hub: per-engine search switches
(Nov 25 2026)

Extends the search control file (/home/asl/ai_search_control.json) with
two engine flags alongside the master switch:

    {"enabled": true/false, "google": true/false, "ddg": true/false}

Missing keys default to ON, so the current file ({"enabled": ...}) keeps
working unchanged. Behavior:

- Google grounded routes are built only when master AND google are on
  (plus the existing search gate and spent-for-the-day rules).
- The DuckDuckGo backup now engages when Google is unavailable for
  EITHER reason - spent for the day OR manually switched off - as long
  as master AND ddg are on. That makes DDG-only testing possible from
  the dashboard: flip Google off and DDG answers search questions.
- Master off still wins over everything: no Google, no DDG. (This also
  closes a gap in the original DDG patch, whose engage check did not
  look at the manual switch at all.)

Safety: every anchor must match exactly once or the patch aborts with
no changes. The new source is compiled in memory BEFORE anything is
written; a timestamped backup is taken; result must py_compile.

Run with:  sudo python3 patch_hub_search_engines.py
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

# --- Edit 1: the DDG backup honors master + ddg, and engages when
# Google is manually off as well as when it is spent ---
old_ddg = """    if _st0.get("grounding_dead") and _gate_low and any(w in _gate_low for w in _search_words):"""
new_ddg = """    _ctl0 = {}
    try:
        with open("/home/asl/ai_search_control.json") as _cf0:
            _ctl0 = json.load(_cf0)
    except Exception:
        _ctl0 = {}
    _master0 = bool(_ctl0.get("enabled", True))
    _google0 = bool(_ctl0.get("google", True))
    _ddg0 = bool(_ctl0.get("ddg", True))
    if _master0 and _ddg0 and (_st0.get("grounding_dead") or not _google0) and _gate_low and any(w in _gate_low for w in _search_words):"""

# --- Edit 2: neutral DDG log line (it no longer only means "spent") ---
old_log = """            ts_log("DDG", "Google search spent for today; answering with DuckDuckGo results.")"""
new_log = """            ts_log("DDG", "Answering with DuckDuckGo results (Google spent or switched off).")"""

# --- Edit 3: the route builder also reads the google flag ---
old_ctl = """    _search_on = True
    try:
        with open("/home/asl/ai_search_control.json") as _cf:
            _search_on = bool(json.load(_cf).get("enabled", True))
    except Exception:
        _search_on = True"""
new_ctl = """    _search_on = True
    _google_on = True
    try:
        with open("/home/asl/ai_search_control.json") as _cf:
            _ctl = json.load(_cf)
        _search_on = bool(_ctl.get("enabled", True))
        _google_on = bool(_ctl.get("google", True))
    except Exception:
        _search_on = True
        _google_on = True"""

# --- Edit 4: grounded routes require the google switch too ---
old_route = """        if _want_search and _search_on and not _state.get("grounding_dead"):"""
new_route = """        if _want_search and _search_on and _google_on and not _state.get("grounding_dead"):"""

EDITS = [
    ("ddg", old_ddg, new_ddg),
    ("log", old_log, new_log),
    ("ctl", old_ctl, new_ctl),
    ("route", old_route, new_route),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-engines"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
