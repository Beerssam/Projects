#!/usr/bin/env python3
"""patch_hub_searxng.py - AI hub: fallback search DDG -> local SearXNG
(Nov 25 2026)

DuckDuckGo bot-walls this network on both its html and lite
endpoints (verified Nov 25: 15 KB challenge pages, 0 results), so
the hub's fallback search never returned a single result - the
ddg_searches counter stayed at zero while the model answered from
memory and occasionally hallucinated. SearXNG now runs on the hub
itself (Docker, 127.0.0.1:8080, JSON API; install_searxng.sh) and
returns real results.

This patch rewires the existing fallback to SearXNG:
- get_ddg_results() becomes get_searxng_results(): same fail-silent
  shape, but it queries http://127.0.0.1:8080/search?format=json
  and reads title/content pairs from the JSON results.
- The prompt block now says the results come from the hub's local
  SearXNG search.
- The log line is tagged [SEARXNG].

Deliberately NOT renamed (internal plumbing, invisible to the
operator, and shared with the dashboard): the ddg_block variable,
the "ddg_searches" state counter, and the "ddg" flag in
ai_search_control.json. The dashboard patch renames everything
the operator actually sees.

Safety: every anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_hub_searxng.py
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

# --- Edit 1: the fetcher's name and docstring ---
old_def = '''def get_ddg_results(query):
    """Best-effort DuckDuckGo HTML search. Returns a prompt block with the
    top results, or "" on any problem (fail-silent)."""'''
new_def = '''def get_searxng_results(query):
    """Best-effort search via the hub's local SearXNG (127.0.0.1:8080,
    JSON API). Returns a prompt block with the top results, or "" on
    any problem (fail-silent)."""'''

# --- Edit 2: the fetch URL ---
old_url = '''        _url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)'''
new_url = '''        _url = "http://127.0.0.1:8080/search?q=" + urllib.parse.quote_plus(query) + "&format=json"'''

# --- Edit 3: fetch + parse (HTML scraping -> JSON results) ---
old_parse = '''        _resp = requests.get(_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}, timeout=8)
        _page = _resp.text
        _titles = []
        for _m in _re.finditer(r'class="result__a"[^>]*>(.*?)</a>', _page, _re.S):
            _titles.append(_htmlmod.unescape(_re.sub(r"<[^>]+>", "", _m.group(1))).strip())
            if len(_titles) >= 5:
                break
        _snips = []
        for _m in _re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', _page, _re.S):
            _snips.append(_htmlmod.unescape(_re.sub(r"<[^>]+>", "", _m.group(1))).strip())
            if len(_snips) >= 5:
                break'''
new_parse = '''        _resp = requests.get(_url, headers={"Accept": "application/json"}, timeout=10)
        _titles = []
        _snips = []
        for _r in _resp.json().get("results", []):
            _titles.append((_r.get("title") or "").strip())
            _snips.append((_r.get("content") or "").strip())
            if len(_titles) >= 5:
                break'''

# --- Edit 4: the prompt block header ---
old_head = '''        return ("WEB SEARCH RESULTS (from DuckDuckGo - Google search is spent for today; use these results to answer questions needing current information):\\n"'''
new_head = '''        return ("WEB SEARCH RESULTS (from the hub's local SearXNG search - Google search is spent or off; use these results to answer questions needing current information):\\n"'''

# --- Edit 5: the call site ---
old_call = '''        ddg_block = get_ddg_results(_gate_low)'''
new_call = '''        ddg_block = get_searxng_results(_gate_low)'''

# --- Edit 6: the log line ---
old_log = '''            ts_log("DDG", "Answering with DuckDuckGo results (Google spent or switched off).")'''
new_log = '''            ts_log("SEARXNG", "Answering with local SearXNG results (Google spent or switched off).")'''

EDITS = [
    ("def", old_def, new_def),
    ("url", old_url, new_url),
    ("parse", old_parse, new_parse),
    ("head", old_head, new_head),
    ("call", old_call, new_call),
    ("log", old_log, new_log),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searxng"
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
