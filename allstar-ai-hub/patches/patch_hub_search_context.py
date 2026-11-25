#!/usr/bin/env python3
"""patch_hub_search_context.py - AI hub: carry the previous
exchange's context into SearXNG queries (Nov 25 2026)

Sam's test, Nov 25 17:21: after a successful parks search, the
follow-up "Where is that field or area located at? And can you
Google and search are there any other areas..." DID search - but
the query went out as 'field area located at? google search other
areas fly remote controlled aircraft?' with no place in it,
because the query is built only from the current transmission
and the question named no place ("that field"). 29 generic
results, none with the address, and the hub honestly reported
its results did not show the location.

Fix: when the fallback search fires, append the previous
exchange's text (from global_state["history"][-1] - at this
point in process_audio that is still the PREVIOUS exchange; the
current one is appended later) to the query string. The existing
cleaner then strips it to keywords, dedupes against the current
question's words (which stay first, so they dominate), and the
place/subject terms ride along: the query above becomes
'... aircraft? shawnee kansas mission radio control club ...'
and can actually answer "where".

Robustness: the history entry's exact shape is not assumed -
it is stringified, reduced to letters/spaces, and the role words
'user'/'assistant' are dropped. The whole merge sits in a
try/except: any surprise falls back to the plain current-question
query, exactly today's behavior. The final cleaned query is
already logged under [SEARXNG], so the merge stays visible.

Companion tweak: the cleaner's keyword cap rises 14 -> 18 so the
context terms are not cut off by the current question's words
(a lone question rarely cleans past 14 anyway; the Raytown
transcript cleaned to ~13).

Safety: every anchor must match exactly once or the patch aborts
with no changes; an already-applied guard covers reruns; compiled
in memory before writing; timestamped backup; py_compile check.

Run with:  sudo python3 patch_hub_search_context.py
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

if "get_searxng_results(_q)" in src:
    print("ABORT: context merge already present (patch already applied?). No changes made.")
    sys.exit(1)

# --- Edit 1: merge the previous exchange into the search query ---
old_call = '''        ddg_block = get_searxng_results(_gate_low)'''
new_call = '''        _q = _gate_low
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

# --- Edit 2: cleaner keyword cap 14 -> 18 (code + docstring) ---
old_cap = '''    return " ".join(_words[:14]) if _words else query'''
new_cap = '''    return " ".join(_words[:18]) if _words else query'''
old_doc = '''drop bare digits, dedupe, cap at 14 words.'''
new_doc = '''drop bare digits, dedupe, cap at 18 words.'''

EDITS = [
    ("call", old_call, new_call),
    ("cap", old_cap, new_cap),
    ("doc", old_doc, new_doc),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searchcontext"
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
