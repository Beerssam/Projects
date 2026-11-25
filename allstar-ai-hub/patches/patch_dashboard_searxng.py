#!/usr/bin/env python3
"""patch_dashboard_searxng.py - AI hub dashboard: DDG -> SEARXNG labels
(Nov 25 2026)

Companion to patch_hub_searxng.py. The fallback search engine is
now the hub's local SearXNG, not DuckDuckGo (DDG bot-walls this
network; it never returned a single result). This patch renames
everything the operator sees:

- The third switch in the GEMINI POOL stack: DDG -> SEARXNG
  (and its tooltip, if present).
- The status line variants: "DDG backup used Mx" -> "SEARXNG
  backup used Mx"; "DDG ONLY (Google off)" -> "SEARXNG ONLY
  (Google off)"; "N DDG searches today" -> "N SEARXNG searches
  today".

Internal names (element ids, the ddg_searches API field, the
control-file flag) are unchanged - they are plumbing shared with
the orchestrator, and the values they carry are now SearXNG's.

Safety: every required anchor must match exactly once or the
patch aborts with no changes (the tooltip edit is soft: applied
only if present exactly once). Compiled in memory before
writing; timestamped backup; result must py_compile.

Run with:  sudo python3 patch_dashboard_searxng.py
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

EDITS = [
    ("label",
     '<div style="display:flex; align-items:center; justify-content:flex-end; gap:6px;">DDG ',
     '<div style="display:flex; align-items:center; justify-content:flex-end; gap:6px;">SEARXNG '),
    ("spent",
     "' searches today \u00b7 DDG backup used '",
     "' searches today \u00b7 SEARXNG backup used '"),
    ("only",
     "'WEB SEARCH: DDG ONLY (Google off) \u00b7 '",
     "'WEB SEARCH: SEARXNG ONLY (Google off) \u00b7 '"),
    ("count",
     "' DDG searches today'",
     "' SEARXNG searches today'"),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searxng"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

# Soft edit: the switch tooltip, only if it is there exactly once.
_tip_old = 'title="Toggle DuckDuckGo search"'
if src.count(_tip_old) == 1:
    src = src.replace(_tip_old, 'title="Toggle SearXNG local search"')

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_dashboard")
