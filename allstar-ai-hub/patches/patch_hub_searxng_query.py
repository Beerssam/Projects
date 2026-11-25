#!/usr/bin/env python3
"""patch_hub_searxng_query.py - AI hub: clean the SearXNG query and
log every search attempt (Nov 25 2026)

Diagnosis (Nov 25, 11:01-11:25): the fallback fetch fired but came
back empty, invisibly. Sam curled SearXNG directly with the exact
Whisper transcript of his question ("this is kilo box truck 0 romeo
in kyuzulu doing a hub ai test does the news say anything specific
about an incident in raytown missouri...") and SearXNG returned 0
results - while a clean typed query ("Raytown Missouri police
officer killed") returns 20. The engine is healthy; the raw radio
transcript is simply a terrible search query: engines choke on
25 words of callsign chatter, phonetic spelling, and filler.

Two changes inside the fallback path:

1. _searxng_clean_query(): reduces the transcript to keywords -
   drops filler/stopwords, drops phonetic-alphabet words (NATO and
   police styles - operators spell names with them, and spelled
   letters are noise to a search engine), drops bare digits,
   dedupes, caps at 14 words. If SearXNG still returns nothing and
   the cleaned query is long, one retry with just the last 6 words
   (the actual question usually sits at the end of a transmission,
   after the ID preamble).

2. Visibility: the fetcher now logs every attempt under [SEARXNG]
   with the cleaned query and the result count, and logs the
   exception type on failure. Fail-silent hid this entire failure
   class for a day; it will not hide again. Behavior is otherwise
   unchanged: a failed/empty search still just means the question
   is answered without a results block.

Safety: every anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_hub_searxng_query.py
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

# --- Edit 1: the query cleaner, just before the fetcher ---
old_def = '''def get_searxng_results(query):'''
new_def = '''def _searxng_clean_query(query):
    """Reduce a raw radio transcript to search keywords: drop filler
    and phonetic-alphabet words (operators spell names with them),
    drop bare digits, dedupe, cap at 14 words."""
    _stop = {"a", "an", "the", "is", "are", "was", "were", "do", "does", "did", "you", "i", "me", "my", "we", "it", "its", "this", "that", "there", "here", "and", "or", "of", "to", "in", "on", "for", "with", "about", "anything", "say", "says", "said", "tell", "please", "hey", "okay", "ok", "um", "uh", "can", "could", "would", "what", "when", "where", "who", "whom", "how", "any", "some", "im", "i'm", "lets", "let", "get", "got", "doing", "spell", "spells", "spelled", "asking", "specifically"}
    _phon = {"alfa", "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliett", "kilo", "lima", "mike", "november", "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey", "xray", "x-ray", "yankee", "zulu", "adam", "boy", "charles", "david", "edward", "frank", "george", "henry", "ida", "john", "king", "lincoln", "mary", "nora", "ocean", "paul", "queen", "robert", "sam", "tom", "union", "william", "young", "zebra"}
    _words = []
    for _w in query.lower().replace(",", " ").replace(".", " ").split():
        if _w in _stop or _w in _phon:
            continue
        if _w.isdigit():
            continue
        if _w not in _words:
            _words.append(_w)
    return " ".join(_words[:14]) if _words else query

def get_searxng_results(query):'''

# --- Edit 2: clean the query, retry with the tail, log the attempt ---
old_fetch = '''        _url = "http://127.0.0.1:8080/search?q=" + urllib.parse.quote_plus(query) + "&format=json"
        _resp = requests.get(_url, headers={"Accept": "application/json"}, timeout=10)
        _titles = []
        _snips = []
        for _r in _resp.json().get("results", []):'''
new_fetch = '''        _clean = _searxng_clean_query(query)
        _url = "http://127.0.0.1:8080/search?q=" + urllib.parse.quote_plus(_clean) + "&format=json"
        _resp = requests.get(_url, headers={"Accept": "application/json"}, timeout=10)
        _results = _resp.json().get("results", [])
        if not _results and len(_clean.split()) > 6:
            _clean = " ".join(_clean.split()[-6:])
            _url = "http://127.0.0.1:8080/search?q=" + urllib.parse.quote_plus(_clean) + "&format=json"
            _resp = requests.get(_url, headers={"Accept": "application/json"}, timeout=10)
            _results = _resp.json().get("results", [])
        ts_log("SEARXNG", f"Query '{_clean}' returned {len(_results)} results.")
        _titles = []
        _snips = []
        for _r in _results:'''

# --- Edit 3: log failures instead of swallowing them ---
old_except = '''                + "\\n".join(_lines) + "\\n\\n")
    except Exception:
        return ""'''
new_except = '''                + "\\n".join(_lines) + "\\n\\n")
    except Exception as _e:
        try:
            ts_log("SEARXNG", f"Search failed: {type(_e).__name__}")
        except Exception:
            pass
        return ""'''

EDITS = [
    ("def", old_def, new_def),
    ("fetch", old_fetch, new_fetch),
    ("except", old_except, new_except),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searxngquery"
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
