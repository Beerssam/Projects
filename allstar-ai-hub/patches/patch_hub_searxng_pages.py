#!/usr/bin/env python3
"""patch_hub_searxng_pages.py - AI hub: deepen SearXNG results with
actual page text (Nov 25 2026)

Sam-requested audit, Nov 25 18:04: the search mechanics are now
correct (clean queries, right store found - Cosentino's Price
Chopper, 22210 W 66th St), but the hub keeps answering "the
results mention hours of operation but do not display the
specific times." It is telling the truth about what it is handed:
the results block is 5 titles + short snippets, and page facts
(store hours, addresses, phone numbers) live inside the pages,
not in the snippets.

Fix, inside get_searxng_results, after the snippet lines are
built and before the block is returned:

1. If SearXNG's JSON carries infobox content, surface it as an
   INFO line.
2. Fetch the top 2 result pages (browser UA, 5 s timeout each)
   and append a PAGE TEXT section per page: scripts/styles
   stripped, tags removed, whitespace collapsed; the window is
   centered on the first fact keyword (hours / monday / open /
   a.m. / p.m.) when one appears deep in the page, else the
   first ~1800 chars. Any "openingHours" data found in the raw
   HTML (JSON-LD) is surfaced first as a HOURS DATA line.
3. A [SEARXNG] log line records how many pages were deepened.

Everything is fail-silent per page and overall: any fetch or
parse problem leaves the snippet block exactly as it was today.
Worst-case added latency is ~2 x 5 s on a hanging site; typical
is a second or two.

Safety: the anchor must match exactly once or the patch aborts
with no changes; an already-applied guard covers reruns;
compiled in memory before writing; timestamped backup; result
must py_compile.

Run with:  sudo python3 patch_hub_searxng_pages.py
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

if "PAGE TEXT from" in src:
    print("ABORT: page deepening already present (patch already applied?). No changes made.")
    sys.exit(1)

old = '''        _lines = []
        for _i, _t in enumerate(_titles):
            _s = _snips[_i] if _i < len(_snips) else ""
            _lines.append(f"- {_t}: {_s}" if _s else f"- {_t}")
        return ("WEB SEARCH RESULTS (from the hub's local SearXNG search - Google search is spent or off; use these results to answer questions needing current information):\\n"'''
new = '''        _lines = []
        for _i, _t in enumerate(_titles):
            _s = _snips[_i] if _i < len(_snips) else ""
            _lines.append(f"- {_t}: {_s}" if _s else f"- {_t}")
        # Deepen: snippets rarely carry page facts (hours, addresses,
        # phone numbers). Surface any SearXNG infobox, then fetch the
        # top 2 result pages and include their text. Fail-silent.
        try:
            _data = _resp.json()
            for _ib in (_data.get("infoboxes") or [])[:1]:
                _c = (_ib.get("content") or "").strip()
                if _c:
                    _lines.append("INFO: " + _c[:600])
        except Exception:
            pass
        _fetched = 0
        for _r in _results:
            if _fetched >= 2:
                break
            _u = (_r.get("url") or "").strip()
            if not _u.startswith("http"):
                continue
            try:
                _pr = requests.get(_u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}, timeout=5)
                _raw = _pr.text or ""
                _oh = _raw.lower().find("openinghours")
                if _oh >= 0:
                    _seg = _re.sub(r"(?s)<[^>]+>", " ", _raw[_oh:_oh + 300])
                    _seg = " ".join(_htmlmod.unescape(_seg).split())
                    if _seg:
                        _lines.append("HOURS DATA: " + _seg)
                _txt = _re.sub(r"(?is)<(script|style).*?</\\1>", " ", _raw)
                _txt = _re.sub(r"(?s)<[^>]+>", " ", _txt)
                _txt = " ".join(_htmlmod.unescape(_txt).split())
                if len(_txt) < 200:
                    continue
                _low = _txt.lower()
                _pos = -1
                for _kw in ("hours", "monday", "open", "a.m.", "p.m."):
                    _pos = _low.find(_kw)
                    if _pos >= 0:
                        break
                if _pos > 400:
                    _txt = _txt[_pos - 200:_pos + 1600]
                else:
                    _txt = _txt[:1800]
                _lines.append(f"PAGE TEXT from {_u}: {_txt}")
                _fetched += 1
            except Exception:
                continue
        if _fetched:
            try:
                ts_log("SEARXNG", f"Deepened with text from {_fetched} page(s).")
            except Exception:
                pass
        return ("WEB SEARCH RESULTS (from the hub's local SearXNG search - Google search is spent or off; use these results to answer questions needing current information):\\n"'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searxngpages"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
