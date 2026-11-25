#!/usr/bin/env python3
"""patch_hub_search_fallback.py - AllStar AI Hub: fail-soft web search (Nov 24 2026)

Problem: every orchestrator request carries Google Search grounding, and
grounding has its OWN free daily allowance, separate from the model quota.
When that allowance is exhausted, every request returns 429 - even though
the model itself has quota left - and the hub answers "Full pool
exhaustion" to everything (proven by A/B curl tests Nov 24).

Fix: the key-pool loop now runs up to two passes. Pass 1 is unchanged
(grounded requests, rotating keys on 429/503). If every key refuses, pass 2
retries the whole pool with the SAME payload minus the search tool, so the
hub still answers from the model plus its injected ADS-B / health /
conversation data - just without live web lookup until the search
allowance resets (~midnight Pacific).

Safety: every anchor must match exactly once or the patch aborts with no
changes. A timestamped backup is written first; result must py_compile.

Run with:  sudo python3 patch_hub_search_fallback.py
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

# --- Edit 1: build an ungrounded copy of the payload right after it ---
old_payload_tail = """        "tools": [{"google_search": {}}]
    }"""
new_payload_tail = """        "tools": [{"google_search": {}}]
    }
    # Ungrounded twin of the payload (no search tool) for the fail-soft
    # second pass - see the loop below.
    _ungrounded = dict(payload)
    _ungrounded.pop("tools", None)"""

# --- Edit 2: the pool loop runs two passes over the keys ---
old_loop = """    for attempt in range(len(GEMINI_KEYS)):
        active_idx = global_state["current_key_idx"]"""
new_loop = """    for attempt in range(2 * len(GEMINI_KEYS)):
        if attempt == len(GEMINI_KEYS):
            ts_log("API", "Search grounding refused by all keys; retrying the pool without web search.")
        active_idx = global_state["current_key_idx"]"""

# --- Edit 3: each attempt posts the payload for its pass ---
old_post = """            response = requests.post(f"{API_URL}?key={active_key}", json=payload, timeout=25)"""
new_post = """            _pl = payload if attempt < len(GEMINI_KEYS) else _ungrounded
            response = requests.post(f"{API_URL}?key={active_key}", json=_pl, timeout=25)"""

for name, old in (("payload", old_payload_tail), ("loop", old_loop), ("post", old_post)):
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-searchfallback"
shutil.copy2(PATH, backup)

src = src.replace(old_payload_tail, new_payload_tail)
src = src.replace(old_loop, new_loop)
src = src.replace(old_post, new_post)
with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
