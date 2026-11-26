#!/usr/bin/env python3
"""patch_hub_backrefs.py - AI hub: widen the back-reference words
that trigger the SearXNG context merge (Nov 25 2026)

patch_hub_search_context2.py gates the context merge on a
back-reference word: that, it, its, there, they, them, he, she.
Sam's live test at 17:59 caught a miss: "Can you Google again
and tell me what THOSE hours of operation are?" - 'those' is not
in the list, so no context merged, the query went out without
the store's name ('google again those hours operation just
normal workdays?'), and 29 generic results could not answer.

Fix: add 'those', 'these' and 'again' to the list. 'Again' is a
follow-up signal in its own right ("Google again", "check
again") and rarely opens a genuinely new topic.

Safety: the anchor must match exactly once or the patch aborts
with no changes; an already-applied guard covers reruns;
compiled in memory before writing; timestamped backup; result
must py_compile.

Run with:  sudo python3 patch_hub_backrefs.py
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

if '"those", "these", "again"' in src:
    print("ABORT: widened back-references already present (patch already applied?). No changes made.")
    sys.exit(1)

old = '''        if any(w in _wl for w in ("that", "it", "its", "there", "they", "them", "he", "she")):'''
new = '''        if any(w in _wl for w in ("that", "it", "its", "there", "they", "them", "he", "she", "those", "these", "again")):'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-backrefs"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
