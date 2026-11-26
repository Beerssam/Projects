#!/usr/bin/env python3
"""patch_hub_fresh_search.py - AI hub: 'new search' / 'search again'
means discard the old answer and re-search (Nov 25 2026)

Sam's design, approved on a voice call Nov 25: the trigger words
(search, google) already force a fresh fetch, but nothing tells
the model to THROW AWAY the previous search's answer - it keeps
leaning on what it said before, which is exactly what frustrated
him in the parks/Price Chopper tests.

Fix: when the gate transcript contains 'new search' or
'search again', the question is treated as an explicit fresh-
search command. The fetch itself is unchanged (the words
'search'/'google' already trigger it), but when the SearXNG
fallback produces a results block for such a question, an
IMPORTANT note is prepended to that block: the user rejected
the previous search, these are the new results, answer from
them, and where they conflict with anything said earlier in
this conversation, the new results are correct and the earlier
answer was wrong.

Scope discipline: the note appears ONLY on questions carrying
one of the two phrases, and only when a fresh results block was
actually produced. Normal questions are untouched.

Safety: every anchor must match exactly once or the patch
aborts with no changes; an already-applied guard covers
reruns; compiled in memory before writing; timestamped backup;
result must py_compile.

Run with:  sudo python3 patch_hub_fresh_search.py
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

if "_fresh" in src:
    print("ABORT: fresh-search rule already present (patch already applied?). No changes made.")
    sys.exit(1)

# --- Edit 1: detect the explicit fresh-search phrases ---
old_ctl = '''    _ddg0 = bool(_ctl0.get("ddg", True))'''
new_ctl = '''    _ddg0 = bool(_ctl0.get("ddg", True))
    _fresh = bool(_gate_low) and ("new search" in _gate_low or "search again" in _gate_low)'''

# --- Edit 2: prepend the discard-the-old-answer note to a fresh block ---
old_call = '''        ddg_block = get_searxng_results(_q)
        if ddg_block:'''
new_call = '''        ddg_block = get_searxng_results(_q)
        if ddg_block and _fresh:
            ddg_block = ("IMPORTANT: The user was not satisfied with the previous search and explicitly asked for a NEW search. "
                         "The results below are from that new search. Answer from these results; if they conflict with anything "
                         "said earlier in this conversation, these results are correct and the earlier answer was wrong.\\n\\n") + ddg_block
        if ddg_block:'''

EDITS = [
    ("ctl", old_ctl, new_ctl),
    ("call", old_call, new_call),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-freshsearch"
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
