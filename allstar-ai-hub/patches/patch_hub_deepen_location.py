#!/usr/bin/env python3
"""patch_hub_deepen_location.py - AI hub: deepening picks the
pages that match the question's terms, not just the top-ranked
ones (Nov 25 2026)

The page deepening (patch_hub_searxng_pages.py) fetches the top
2 SearXNG results and hands their text to the model. Ranking is
not relevance: at 19:50 on Nov 25 the Sunday-hours follow-up
deepened two pages for a DIFFERENT Price Chopper location, and
the model - correctly, under the honesty rule - refused to use
another store's hours. The right store's page was in the
results; it was simply never opened.

Fix, inside get_searxng_results' deepening step:
- Fetch up to 4 candidate pages (same per-page extraction as
  today: HOURS DATA + windowed PAGE TEXT), holding each page's
  lines aside instead of appending them directly.
- Score each page by how many distinct content words from the
  cleaned query (_clean, minus fact/function words like day
  names, hours/open/close, search/google) appear in its title +
  text. A page about the asked-about place matches the place
  words (shawnee, west, 66th, street); a same-named store in
  another town matches only the subject words.
- Keep the best 2 by score (ties keep search rank), restore
  rank order, and append those to the results block. When the
  query yields no content terms, behaviour is exactly today's:
  the first 2 pages by rank.

Fail-silent per page and overall, exactly as today; the
[SEARXNG] "Deepened with text from N page(s)." log line is
unchanged. Worst case adds ~2 extra page fetches (~1 s typical).

Safety: requires the pages patch to be present; anchor must
match exactly once or the patch aborts with no changes; an
already-applied guard covers reruns; compiled in memory before
writing; timestamped backup; result must py_compile.

Run with:  sudo python3 patch_hub_deepen_location.py
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

if "_cands = []" in src:
    print("ABORT: location-scored deepening already present (patch already applied?). No changes made.")
    sys.exit(1)
if "PAGE TEXT from" not in src:
    print("ABORT: page deepening not found - apply patch_hub_searxng_pages.py first. No changes made.")
    sys.exit(1)

old = '''        _fetched = 0
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
                pass'''

new = '''        _skipw = {"hours", "hour", "open", "opens", "opened", "close", "closes", "closed", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "today", "tonight", "tomorrow", "day", "week", "latest", "what", "when", "time", "search", "google", "new", "again", "tell", "operation", "operations"}
        _terms = []
        for _w in _re.sub(r"[^a-z0-9 ]", " ", (_clean or "").lower()).split():
            if len(_w) >= 3 and _w not in _skipw and _w not in _terms:
                _terms.append(_w)
        _cands = []
        _ridx = 0
        for _r in _results:
            if len(_cands) >= 4:
                break
            _ridx += 1
            _u = (_r.get("url") or "").strip()
            if not _u.startswith("http"):
                continue
            try:
                _plines = []
                _pr = requests.get(_u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}, timeout=5)
                _raw = _pr.text or ""
                _oh = _raw.lower().find("openinghours")
                if _oh >= 0:
                    _seg = _re.sub(r"(?s)<[^>]+>", " ", _raw[_oh:_oh + 300])
                    _seg = " ".join(_htmlmod.unescape(_seg).split())
                    if _seg:
                        _plines.append("HOURS DATA: " + _seg)
                _txt = _re.sub(r"(?is)<(script|style).*?</\\1>", " ", _raw)
                _txt = _re.sub(r"(?s)<[^>]+>", " ", _txt)
                _txt = " ".join(_htmlmod.unescape(_txt).split())
                if len(_txt) < 200 and not _plines:
                    continue
                _score = 0
                if _terms:
                    _hay = ((_r.get("title") or "") + " " + _txt).lower()
                    _score = sum(1 for _w in _terms if _w in _hay)
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
                _plines.append(f"PAGE TEXT from {_u}: {_txt}")
                _cands.append((_score, _ridx, _plines))
            except Exception:
                continue
        if _terms and len(_cands) > 2:
            _cands = sorted(_cands, key=lambda _c: (-_c[0], _c[1]))[:2]
            _cands = sorted(_cands, key=lambda _c: _c[1])
        else:
            _cands = _cands[:2]
        _fetched = 0
        for _sc, _ri, _pl in _cands:
            _lines.extend(_pl)
            _fetched += 1
        if _fetched:
            try:
                ts_log("SEARXNG", f"Deepened with text from {_fetched} page(s).")
            except Exception:
                pass'''

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-deepenloc"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
