#!/usr/bin/env python3
"""patch_hub_search_context2.py - AI hub: only carry context into
a search when the question actually refers back (Nov 25 2026)

patch_hub_search_context.py (applied 17:47) merged the previous
exchange's keywords into EVERY fallback search. Sam's test at
17:52 proved that too greedy: a brand-new topic - "Can you Google
the hours of operation for the Price Chopper in Western Shawnee
off of 66th Street?" - went out as 'google hours operation price
chopper western chawnee off 66th street? want fly remote
controlled aircraft de soto kansas'. The old topic's words
poisoned the results (29 of them, none about Price Chopper), and
the hub - honestly, per the new prompt rules - reported its
results did not show the hours. From the operator's chair that
reads as "it refused to Google"; in fact it Googled with one
hand tied.

Fix: the context merge now happens ONLY when the current
question refers back to the previous exchange - it contains a
back-reference word (that, it, its, there, they, them, he, she).
"Where is THAT field located?" merges and gets its place terms;
a self-contained new question searches clean. The context words
are also scrubbed harder: tokens of 2 letters or fewer and
reply-meta words (search, results, current, copy, ...) no longer
ride along eating keyword slots.

Safety: the anchor is the exact block inserted by
patch_hub_search_context.py and must match exactly once or the
patch aborts with no changes; an already-applied guard covers
reruns; compiled in memory before writing; timestamped backup;
result must py_compile.

Run with:  sudo python3 patch_hub_search_context2.py
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

if "_wl = _gate_low.replace" in src:
    print("ABORT: back-reference gate already present (patch already applied?). No changes made.")
    sys.exit(1)

old = '''        _q = _gate_low
        try:
            _hist0 = global_state.get("history", [])
            if _hist0:
                _raw = "".join(c if (c.isalpha() or c.isspace()) else " " for c in str(_hist0[-1]).lower())
                _ctx = " ".join(w for w in _raw.split() if w not in ("user", "assistant"))
                if _ctx:
                    _q = _gate_low + " " + _ctx
        except Exception:
            _q = _gate_low
        ddg_block = get_searxng_results(_q)'''
new = '''        _q = _gate_low
        _wl = _gate_low.replace("?", " ").replace(".", " ").replace(",", " ").split()
        if any(w in _wl for w in ("that", "it", "its", "there", "they", "them", "he", "she")):
            try:
                _hist0 = global_state.get("history", [])
                if _hist0:
                    _raw = "".join(c if (c.isalpha() or c.isspace()) else " " for c in str(_hist0[-1]).lower())
                    _ctx = " ".join(w for w in _raw.split() if len(w) > 2 and w not in ("user", "assistant", "search", "results", "result", "current", "copy", "hello", "saying", "show", "shows"))
                    if _ctx:
                        _q = _gate_low + " " + _ctx
            except Exception:
                _q = _gate_low
        ddg_block = get_searxng_results(_q)'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searchcontext2"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
