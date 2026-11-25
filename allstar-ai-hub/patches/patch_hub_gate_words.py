#!/usr/bin/env python3
"""patch_hub_gate_words.py - AI hub: widen the search gate's trigger
words (Nov 25 2026)

Sam's catches:
- "president" was not a trigger, so "name the president" (no
  "who is") answered from stale training data. It is his standard
  test question; the word now triggers a live search.
- The explicit commands "search" / "look up" were not triggers at
  all - the most reliable signal a caller can give. Added, along
  with "lookup" and "google" (as in "google the phone number").

Matching is substring-based on the lowercased transcript, so
"search" also covers "searching"/"research" - both genuinely want
a lookup anyway. The gate still fails open on an empty transcript,
and a fired gate still just ATTACHES the search tool: Google
grounding first, DDG only when Google is spent or switched off.

Safety: the anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_hub_gate_words.py
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

old = '''    _search_gate_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is")'''
new = '''    _search_gate_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is", "president", "search", "look up", "lookup", "google")'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-gatewords"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
