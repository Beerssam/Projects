#!/usr/bin/env python3
"""patch_hub_empty_retry.py - AI hub: one retry when Gemini
returns empty + stop reply meta-words leaking into merged
search queries (Nov 25 2026)

Two fixes from the Nov 25 20:47-20:49 Walmart pharmacy tests:

1. EMPTY-RETRY. Attempt 3 was heard perfectly by the gate
   ('...pharmacy at the Walmart off of 65th Street in Shawnee'),
   the search ran, and then Gemini returned a 200 with EMPTY
   transcript and reply. The SAFEGUARD dropped it ("No actionable
   human speech parsed") and the question died in silence - from
   the radio it feels like the hub ignored you. Fix: when the
   parsed result is empty in BOTH fields AND the Whisper gate
   heard a real-looking question (transcript >= 10 chars, not a
   bracketed non-speech tag like [MUSIC PLAYING]), rotate the
   key and retry the request ONCE. A second empty drops as
   today. Junk clips are unaffected: empty gate transcripts and
   bracketed tags never retry, and [noise]/[id]/cw safeguard
   cases keep their existing drop.

2. SCRUB. Attempt 2's merged query contained 'not specify' -
   words from the hub's own previous refusal leaking through the
   context merge. Add specify / specified / still / not to the
   merge scrub tuple (patch_hub_search_context2.py's list).

Safety: both anchors must match exactly once or the patch
aborts with no changes; an already-applied guard covers
reruns; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_hub_empty_retry.py
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

if "_empty_retried" in src:
    print("ABORT: empty-retry already present (patch already applied?). No changes made.")
    sys.exit(1)

# --- Edit 1a: retry flag + gate-transcript snapshot before the loop ---
old1a = '''    _codes = []
    for attempt in range(len(_routes) * len(GEMINI_KEYS)):'''
new1a = '''    _codes = []
    _empty_retried = False
    _gl = _gate_low if isinstance(_gate_low, str) else ""
    for attempt in range(len(_routes) * len(GEMINI_KEYS)):'''

# --- Edit 1b: on a both-fields-empty parse, retry once if the
# gate heard a real question ---
old1b = '''                if not ai_reply or user_transcript.strip().lower() in ["", "[noise]", "[noise] ", "[id]", "cw", "morse", "[static]"]:
                    ts_log("SAFEGUARD", "No actionable human speech parsed. Dropping transmission response.")
                    return None'''
new1b = '''                if not ai_reply or user_transcript.strip().lower() in ["", "[noise]", "[noise] ", "[id]", "cw", "morse", "[static]"]:
                    if not ai_reply and not user_transcript.strip() and not _empty_retried and len(_gl) >= 10 and not _gl.startswith("["):
                        _empty_retried = True
                        ts_log("SAFEGUARD", "Gemini returned empty for a clip the gate heard clearly; retrying once with the next key.")
                        global_state["current_key_idx"] = (active_idx + 1) % len(GEMINI_KEYS)
                        continue
                    ts_log("SAFEGUARD", "No actionable human speech parsed. Dropping transmission response.")
                    return None'''

# --- Edit 2: scrub reply meta-words out of merged context ---
old2 = '''                    _ctx = " ".join(w for w in _raw.split() if len(w) > 2 and w not in ("user", "assistant", "search", "results", "result", "current", "copy", "hello", "saying", "show", "shows"))'''
new2 = '''                    _ctx = " ".join(w for w in _raw.split() if len(w) > 2 and w not in ("user", "assistant", "search", "results", "result", "current", "copy", "hello", "saying", "show", "shows", "specify", "specified", "still", "not"))'''

for label, old in (("1a", old1a), ("1b", old1b), ("2", old2)):
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor {label} found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-emptyretry"
shutil.copy2(PATH, backup)
src = src.replace(old1a, new1a).replace(old1b, new1b).replace(old2, new2)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
