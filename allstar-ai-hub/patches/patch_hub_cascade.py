#!/usr/bin/env python3
"""patch_hub_cascade.py - AllStar AI Hub: model cascade + usage state (Nov 25 2026)

Turns the single-model key pool into a cascade of free Gemini models.

Cascade order (smartest first; daily free-tier request caps are per model
per project, so each rung is a separate bucket):
    1. gemini-2.5-flash        (~20/day)  - smartest, small bucket
    2. gemini-3.5-flash-lite   (~500/day) - the Dec 1 auto-route target
    3. gemini-3.1-flash-lite   (~500/day)

Behavior:
- For each model, keys are tried with search grounding first (unless
  grounding is already known dead today), then without search.
- A model whose keys all refuse with 429 is marked EXHAUSTED for the rest
  of the quota day and skipped instantly by later questions. (503s do NOT
  mark a model exhausted - an outage is not an empty bucket.)
- If every key refuses a grounded pass with 429, grounding is marked dead
  for the day and later questions skip straight to ungrounded - no more
  ~7 s of doomed retries before each answer.
- Quota day = the Pacific date (Google resets free quotas at midnight PT).
- Usage is recorded in /home/asl/ai_model_state.json (per model: requests
  used, answers given, exhausted flag, cap; plus grounding state and the
  current model) for the dashboard's GEMINI POOL panel.

Note for after Dec 1, 2026: rung 1 (2.5 Flash) auto-routes to 3.5
Flash-Lite, so swap rung 1 to gemini-3.8-flash then if a smart-first rung
is still wanted. CASCADE_MODELS below is the one line to change.

Safety: every anchor must match exactly once or the patch aborts with no
changes. A timestamped backup is written first; result must py_compile.

Run with:  sudo python3 patch_hub_cascade.py
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

# --- Edit 1: cascade config + state helpers, right after API_URL ---
old_url = 'API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"'
new_url = old_url + '''

# --- Model cascade (Nov 25 2026) ---
# (model, free daily request cap) in priority order. Caps are the reported
# free-tier values; Google does not guarantee them.
CASCADE_MODELS = [
    ("gemini-2.5-flash", 20),
    ("gemini-3.5-flash-lite", 500),
    ("gemini-3.1-flash-lite", 500),
]
STATE_PATH = "/home/asl/ai_model_state.json"

def _quota_day():
    # Google's free quotas reset at midnight Pacific.
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

def _load_state():
    _day = _quota_day()
    try:
        with open(STATE_PATH) as _f:
            _st = json.load(_f)
        if _st.get("day") != _day:
            raise ValueError("new quota day")
    except Exception:
        _st = {"day": _day, "grounding_dead": False, "current_model": "", "models": {}}
    for _m, _c in CASCADE_MODELS:
        _e = _st["models"].setdefault(_m, {"used": 0, "answered": 0, "exhausted": False})
        _e["cap"] = _c
    return _st

def _save_state(_st):
    try:
        _st["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _tmp = STATE_PATH + ".tmp"
        with open(_tmp, "w") as _f:
            json.dump(_st, _f)
        os.replace(_tmp, STATE_PATH)
    except Exception:
        pass'''

# --- Edit 2: cascade driver replaces the two-pass loop header ---
old_loop = """    for attempt in range(2 * len(GEMINI_KEYS)):
        if attempt == len(GEMINI_KEYS):
            ts_log("API", "Search grounding refused by all keys; retrying the pool without web search.")"""
new_loop = """    _state = _load_state()
    _models = [(_m, _c) for (_m, _c) in CASCADE_MODELS if not _state["models"][_m]["exhausted"]]
    if not _models:
        _models = [CASCADE_MODELS[-1]]
    _routes = []
    for _m, _c in _models:
        if not _state.get("grounding_dead"):
            _routes.append((_m, payload))
        _routes.append((_m, _ungrounded))
    _codes = []
    for attempt in range(len(_routes) * len(GEMINI_KEYS)):
        _model, _pl = _routes[attempt // len(GEMINI_KEYS)]
        if attempt > 0 and attempt % len(GEMINI_KEYS) == 0:
            _pm, _pp = _routes[(attempt // len(GEMINI_KEYS)) - 1]
            if _codes and all(_c2 == 429 for _c2 in _codes):
                if _pm == _model and _pp is payload:
                    _state["grounding_dead"] = True
                    _save_state(_state)
                    ts_log("API", "Search grounding refused by all keys; continuing without web search.")
                elif _pm != _model:
                    _state["models"][_pm]["exhausted"] = True
                    _save_state(_state)
                    ts_log("CASCADE", f"{_pm} is exhausted for today; moving to {_model}.")
            _codes = []
        _state["models"][_model]["used"] = _state["models"][_model].get("used", 0) + 1
        _save_state(_state)"""

# --- Edit 3: post to the route's model (payload now set by the driver) ---
old_post = """            _pl = payload if attempt < len(GEMINI_KEYS) else _ungrounded
            response = requests.post(f"{API_URL}?key={active_key}", json=_pl, timeout=25)"""
new_post = """            response = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{_model}:generateContent?key={active_key}", json=_pl, timeout=25)"""

# --- Edit 4: record every response code so 429 (quota) and 503 (outage)
# --- are told apart when a route ends ---
old_json = """            res_json = response.json()"""
new_json = """            res_json = response.json()
            _codes.append(response.status_code)"""

old_errbranch = """                if error_code in [429, 503]:"""
new_errbranch = """                _codes.append(error_code)
                if error_code in [429, 503]:"""

# --- Edit 5: on a successful response, record the answering model ---
old_raw = """            raw_text = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()"""
new_raw = """            _state["current_model"] = _model
            _state["models"][_model]["answered"] = _state["models"][_model].get("answered", 0) + 1
            _save_state(_state)
            raw_text = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()"""

# --- Edit 6: when the last route fails too, record its end state ---
old_final = """    ts_log("CRITICAL ERROR", "All API keys in the redundancy pool returned resource exhaustion errors.")"""
new_final = """    if _codes and all(_c2 == 429 for _c2 in _codes):
        _lm, _lp = _routes[-1]
        if _lp is payload:
            _state["grounding_dead"] = True
        _state["models"][_lm]["exhausted"] = True
        _save_state(_state)
    ts_log("CRITICAL ERROR", "All API keys in the redundancy pool returned resource exhaustion errors.")"""

EDITS = [
    ("url+helpers", old_url, new_url),
    ("loop", old_loop, new_loop),
    ("post", old_post, new_post),
    ("json", old_json, new_json),
    ("errbranch", old_errbranch, new_errbranch),
    ("raw", old_raw, new_raw),
    ("final", old_final, new_final),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
