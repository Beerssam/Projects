#!/usr/bin/env python3
"""patch_hub_flashlite.py - AllStar AI Hub: switch Gemini model (Nov 24 2026)

Changes the model in API_URL from gemini-2.5-flash to gemini-3.5-flash-lite.
Reason: free-tier daily quota is per model per project. 2.5 Flash sits in
the ~20 requests/day bucket; 3.5 Flash-Lite is reported at ~500/day, and its
bucket is separate - so this also sidesteps today's exhausted 2.5 bucket.
This is also the model Google auto-routes 2.5 Flash to on Dec 1, 2026, so
the switch makes that transition a non-event.

Trial: if Lite's answers, transcription, or search disappoint, roll back
(copy the backup back over ai_orchestrator.py and restart).

Safety: the anchor line must match exactly once or the patch aborts with
no changes. A timestamped backup is written first; result must py_compile.

Run with:  sudo python3 patch_hub_flashlite.py
Then:      sudo systemctl restart ai_orchestrator
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_orchestrator.py"

with open(PATH) as f:
    src = f.read()

old = 'API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"'
new = 'API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"'

n = src.count(old)
if n != 1:
    print(f"ABORT: API_URL anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-flashlite"
shutil.copy2(PATH, backup)

src = src.replace(old, new)
with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Model is now gemini-3.5-flash-lite. Restart: sudo systemctl restart ai_orchestrator")
