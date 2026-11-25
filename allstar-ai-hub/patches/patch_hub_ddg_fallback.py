#!/usr/bin/env python3
"""patch_hub_ddg_fallback.py - AllStar AI Hub: DuckDuckGo backup search
(Nov 25 2026)

Sam's idea: Google search grounding is the primary web search. When the
day's Google grounding allowance is spent (grounding_dead in the state
file), the hub currently answers from the model's own knowledge only.
This patch adds a backup: on days when Google search is spent, questions
that sound like they need current information (weather, news, scores...)
trigger a DuckDuckGo lookup done by the hub itself, and the top results
are handed to the model as a text block - the same pattern as the ADS-B
and hub-health blocks.

Design notes:
- Only engages when grounding_dead is true. A manual search OFF (the
  dashboard switch) still means NO web search at all - the switch is the
  operator's intent and wins over the backup.
- The local Whisper gate transcript is the search query.
- Best-effort and fail-silent: any fetch/parse problem returns "", and
  the question is answered ungrounded exactly as before. DuckDuckGo
  bot-walls some IPs (datacenter IPs get a challenge page); a walled
  fetch simply yields no block.
- Successful DDG lookups are counted in the state file ("ddg_searches")
  so the dashboard can show them.

Safety: every anchor must match exactly once or the patch aborts with no
changes. A timestamped backup is written first; result must py_compile.

Run with:  sudo python3 patch_hub_ddg_fallback.py
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

# --- Edit 1: the DDG fetcher, just before process_audio ---
old_def = """def process_audio(wav_path):
    \"\"\"Encodes transmission and requests response, cycling through keys if a 429 occurs.\"\"\""""
new_def = """def get_ddg_results(query):
    \"\"\"Best-effort DuckDuckGo HTML search. Returns a prompt block with the
    top results, or "" on any problem (fail-silent).\"\"\"
    try:
        import html as _htmlmod
        import re as _re
        import urllib.parse
        _url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
        _resp = requests.get(_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}, timeout=8)
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
                break
        if not _titles:
            return ""
        _lines = []
        for _i, _t in enumerate(_titles):
            _s = _snips[_i] if _i < len(_snips) else ""
            _lines.append(f"- {_t}: {_s}" if _s else f"- {_t}")
        return ("WEB SEARCH RESULTS (from DuckDuckGo - Google search is spent for today; use these results to answer questions needing current information):\\n"
                + "\\n".join(_lines) + "\\n\\n")
    except Exception:
        return ""

def process_audio(wav_path):
    \"\"\"Encodes transmission and requests response, cycling through keys if a 429 occurs.\"\"\""""

# --- Edit 2: build the DDG block after the hub-health block ---
old_health = """    if _want_health:
        health_block = get_hub_health()
    else:
        health_block = \"\""""
new_health = """    if _want_health:
        health_block = get_hub_health()
    else:
        health_block = ""

    # DuckDuckGo backup search: only when Google grounding is spent for
    # the day, and only when the question sounds like it needs current
    # information. The gate transcript is the query. Fail-silent.
    ddg_block = ""
    _search_words = ("weather", "forecast", "news", "score", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "movie times", "open now", "hours")
    try:
        _st0 = _load_state()
    except Exception:
        _st0 = {}
    if _st0.get("grounding_dead") and _gate_low and any(w in _gate_low for w in _search_words):
        ddg_block = get_ddg_results(_gate_low)
        if ddg_block:
            try:
                _st0["ddg_searches"] = _st0.get("ddg_searches", 0) + 1
                _save_state(_st0)
            except Exception:
                pass
            ts_log("DDG", "Google search spent for today; answering with DuckDuckGo results.")"""

# --- Edit 3: include the block in the system instruction ---
old_instr = '        f"{adsb_block}{health_block}"'
new_instr = '        f"{adsb_block}{health_block}{ddg_block}"'

EDITS = [
    ("def", old_def, new_def),
    ("health", old_health, new_health),
    ("instr", old_instr, new_instr),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-ddg"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
