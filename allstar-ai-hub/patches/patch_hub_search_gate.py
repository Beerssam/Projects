#!/usr/bin/env python3
"""patch_hub_search_gate.py - AllStar AI Hub: offer search only when needed
(Nov 25 2026)

Until now the Google search tool was attached to EVERY question - a
greeting or a radio check carried it just like a weather question. That
wastes the day's search allowance and, when the allowance is spent, made
even "hello" wait through refused retries.

This patch adds a gate, the same pattern as the existing ADS-B and
hub-health gates: the local Whisper transcript is checked for words that
signal the question needs current information (weather, news, scores,
prices...). Only then is search offered. Otherwise the question goes
straight to the ungrounded route - faster, and it never touches the
search tank.

- Fail OPEN: if the gate transcript is empty (Whisper failed), search is
  offered, so a real search question is never starved by a bad read.
- The manual dashboard switch and the spent-for-the-day logic are
  unchanged and still win: gate + switch + allowance must all say yes
  before a grounded route is built.
- The DuckDuckGo backup is unchanged: it engages on spent days for the
  same kind of questions.
- A "SEARCH GATE" log line records each skip so the behavior is visible.

Safety: every anchor must match exactly once or the patch aborts with no
changes. The new source is compiled in memory BEFORE anything is written;
a timestamped backup is taken; result must py_compile.

Run with:  sudo python3 patch_hub_search_gate.py
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

# --- Edit 1: the gate decision, right after the hub-health block ---
old_health = """    if _want_health:
        health_block = get_hub_health()
    else:
        health_block = \"\""""
new_health = """    if _want_health:
        health_block = get_hub_health()
    else:
        health_block = ""

    # Search gate: offer web search only when the question sounds like it
    # needs current information (same pattern as the ADS-B/health gates).
    # Fail OPEN on an empty gate transcript so a real search question is
    # never starved by a bad Whisper read.
    _search_gate_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is")
    _want_search = (not _gate_low) or any(w in _gate_low for w in _search_gate_words)"""

# --- Edit 2: the grounded routes require the gate's yes ---
old_routes = """    for _m, _c in _models:
        if _search_on and not _state.get("grounding_dead"):
            _routes.append((_m, payload))"""
new_routes = """    if not _want_search:
        ts_log("SEARCH GATE", "Question does not need web search; skipping it.")
    for _m, _c in _models:
        if _want_search and _search_on and not _state.get("grounding_dead"):
            _routes.append((_m, payload))"""

EDITS = [
    ("health", old_health, new_health),
    ("routes", old_routes, new_routes),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searchgate"
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
