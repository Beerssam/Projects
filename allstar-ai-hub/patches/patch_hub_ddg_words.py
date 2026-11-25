#!/usr/bin/env python3
"""patch_hub_ddg_words.py - AllStar AI Hub: widen the fallback-search trigger
words to match the search gate (Nov 25 2026, DRAFT - not yet applied)

UPDATE Nov 25 ~11:05 CST: Sam picked SearXNG over lite.duckduckgo.com,
installed it (self-test: 20 results for the Raytown query) and applied
patch_hub_searxng.py, which rewires the fetcher to 127.0.0.1:8080. That
patch did NOT touch _search_words, so this bug SURVIVES the rewire: the
fallback trigger is still the narrow DDG-era list, now gating SearXNG.
CORRECTION (MEMORY.md, Nov 25 11:01 CST): SearXNG DID fire once -
counter 0 -> 1, [SEARXNG] line in the log - but for the hub's OWN
echoed reply, while Sam's actual Raytown question got an empty fetch.
So this trigger patch is NOT the explanation for that failed Raytown
test ("news" is already in _search_words, and the fetch ran); the
pending question is why that fetch came back empty (garbled Whisper
query returning 0 results vs a fetch timeout - discriminating curl
given to Sam, pending). This patch stays LATENT but real: a president
question ("look up who the current president is") still never calls
get_searxng_results() in SearXNG-only mode, because none of its words
are in _search_words. Ship it alongside whatever the empty-fetch
diagnostic finds - not as the fix for the Raytown test.

Sam's catch, found by reading the patch files after the Nov 25 tests:
the search-gate patch (patch_hub_gate_words.py) widened
_search_gate_words with "president", "search", "look up", "lookup"
and "google" - but the DuckDuckGo backup uses its OWN separate tuple,
_search_words, which was never widened. So in DDG-only mode a question
like "look up who the current president is" - Sam's standard test -
never even calls get_ddg_results(): none of its words appear in the
DDG list, so the fetch is skipped silently and the model answers from
memory. The Google gate fires (it uses _search_gate_words); the DDG
gate does not.

This patch replaces the DDG tuple with the union of the widened gate
words and the DDG-only extras ("movie times", "hours"), so both
engines trigger on the same questions.

UPDATE Nov 25 17:13 CST: the endpoint question settled itself -
SearXNG is live and proven. And the gap bit in real use today:
in SearXNG-only mode Sam's explicit "do a Google search..." /
"complete a new search..." questions (Shawnee parks / RC planes)
matched NO word in _search_words, so no fetch ran and the hub
answered from conversation memory. Diagnosis proven from the log
+ state file (google:false, ddg:true, searches stuck at 3).
Sam approved the push Nov 25 17:14. Apply now.

Safety: the anchor must match exactly once or the patch aborts with no
changes. The new source is compiled in memory BEFORE anything is
written; a timestamped backup is taken; result must py_compile.

Run with:  sudo python3 patch_hub_ddg_words.py
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

old = '''    _search_words = ("weather", "forecast", "news", "score", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "movie times", "open now", "hours")'''
new = '''    _search_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is", "president", "search", "look up", "lookup", "google", "movie times", "hours")'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-ddgwords"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
