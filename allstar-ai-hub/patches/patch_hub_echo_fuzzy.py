#!/usr/bin/env python3
"""patch_hub_echo_fuzzy.py - AI hub: fuzzy echo match in the Whisper
gate (Nov 25 2026)

The gate drops the hub's own reply audio by comparing the clip's
transcript to the last reply - but only on an EXACT match (after
stripping spaces/punctuation). Playback transcription drifts
("Raytown" comes back as "Raydown", "KF0RIZ" as "K-S-0 Riz"), the
match breaks, and the echo goes to Gemini. Most such slips are
caught silently by the empty-interpretation safeguard, but each
one costs a Gemini call and sometimes a web search, and one
answered "Go ahead" on air (Nov 25 09:53).

Fix: keep the exact match, and add a similarity check - if the
normalized transcript is at least 72% similar to the last reply
(difflib ratio), drop it as an echo too. The fuzzy check only
applies to replies of 40+ normalized characters: short replies
("Roger that. Go ahead.") keep exact-match-only, so a real user
saying a common short phrase is never dropped by resemblance.

Verified against the real Nov 25 12:07 slip: the drifted echo
scores 0.98 similarity (drops), while a genuine question about
the same story scores 0.19 (passes).

Safety: the anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_hub_echo_fuzzy.py
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

old = '''    last_reply = (global_state.get("last_ai_reply") or "").strip().lower()
    if last_reply:
        last_norm = last_reply.replace(" ", "").replace(".", "").replace(",", "")
        if last_norm and norm == last_norm:
            ts_log("WHISPER GATE", "Dropped clip matching our last reply (echo).")
            return False, text'''

new = '''    last_reply = (global_state.get("last_ai_reply") or "").strip().lower()
    if last_reply:
        last_norm = last_reply.replace(" ", "").replace(".", "").replace(",", "")
        if last_norm and norm:
            _echo = norm == last_norm
            if not _echo and len(last_norm) >= 40:
                import difflib
                _echo = difflib.SequenceMatcher(None, norm, last_norm).ratio() >= 0.72
            if _echo:
                ts_log("WHISPER GATE", "Dropped clip matching our last reply (echo).")
                return False, text'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-echofuzzy"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
