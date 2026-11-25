#!/usr/bin/env python3
"""patch_hub_selfaudio_ts.py - AllStar AI Hub orchestrator fixes (Nov 24 2026)

Two changes to /home/asl/ai_orchestrator.py:

1. Whisper gate: drop blank clips and the hub's own node-generated speech
   (station ID beacon, Asterisk link connect/disconnect announcements)
   BEFORE they reach Gemini. The beacon's own monitor recording was passing
   the gate every 10 minutes and burning a full 4-key pool cycle each time;
   [BLANK_AUDIO] clips were passing and burning cycles too.

2. ts_log: include the DATE in every log line ([YYYY-MM-DD HH:MM:SS.mmm])
   so log entries can be told apart by day.

Safety: every anchor must match exactly once or the patch aborts with no
changes. A timestamped backup is written before editing, and the result
must pass py_compile.

After running:  sudo systemctl restart ai_orchestrator
Rollback: copy the backup file back over ai_orchestrator.py and restart.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_orchestrator.py"

with open(PATH) as f:
    src = f.read()

# --- Change 1: dated log timestamps ---
old_ts = """    print(f"[{now.strftime('%H:%M:%S.%f')[:-3]}] [{tag}] {message}")"""
new_ts = """    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [{tag}] {message}")"""

# --- Change 2: gate drops for blank / self / announcement clips ---
old_pass = """    ts_log("WHISPER GATE", f"Passing to Gemini, local transcript: {text!r}")
    global_state["last_gate_text"] = text"""
new_pass = """    _low = (text or "").strip().lower()
    if (
        (not _low)
        or _low in ("[blank_audio]", "[blank audio]")
        or "official intelligence hub" in _low
        or (_low.startswith("mode 6") and ("connected" in _low or "disconnected" in _low))
    ):
        ts_log("WHISPER GATE", f"Dropped self/blank clip: {text!r}")
        return False, text
    ts_log("WHISPER GATE", f"Passing to Gemini, local transcript: {text!r}")
    global_state["last_gate_text"] = text"""

for name, old in (("timestamp", old_ts), ("gate", old_pass)):
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-selfaudio"
shutil.copy2(PATH, backup)

src = src.replace(old_ts, new_ts).replace(old_pass, new_pass)
with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
