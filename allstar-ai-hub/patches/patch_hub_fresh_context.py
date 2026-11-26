#!/usr/bin/env python3
"""patch_hub_fresh_context.py - AI hub: 'new search' / 'search
again' also trigger the SearXNG context merge (Nov 25 2026)

The context merge (patch_hub_search_context2.py, widened by
patch_hub_backrefs.py) fires only when the question contains a
back-reference word. Sam's live test at 19:22 caught the gap:
"Can you do a new search of what the hours of operations are on
Sunday?" - his rewording contained no back-reference word, so no
context merged, the query went out as 'kf0rz new search hours
operations sunday?' with no store in it, and 10 generic results
could not answer. The fresh-search note fired (the answer echoed
it), but the search itself had nothing to stand on.

'New search' / 'search again' are Sam's own command phrases for
"search again about this" - they always refer to the previous
search by construction. This patch makes them trigger the merge
directly, alongside the back-reference words. The current
question's words still lead the query; the previous exchange's
terms trail, capped, exactly as in the existing merge.

Safety: the anchor must match exactly once or the patch aborts
with no changes; an already-applied guard covers reruns;
compiled in memory before writing; timestamped backup; result
must py_compile.

Run with:  sudo python3 patch_hub_fresh_context.py
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

if "_freshq = (" in src:
    print("ABORT: fresh-phrase merge trigger already present (patch already applied?). No changes made.")
    sys.exit(1)

old = '''        _wl = _gate_low.replace("?", " ").replace(".", " ").replace(",", " ").split()
        if any(w in _wl for w in ("that", "it", "its", "there", "they", "them", "he", "she", "those", "these", "again")):'''
new = '''        _wl = _gate_low.replace("?", " ").replace(".", " ").replace(",", " ").split()
        _freshq = ("new search" in _gate_low) or ("search again" in _gate_low)
        if _freshq or any(w in _wl for w in ("that", "it", "its", "there", "they", "them", "he", "she", "those", "these", "again")):'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-freshcontext"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
