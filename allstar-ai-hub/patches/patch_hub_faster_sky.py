#!/usr/bin/env python3
"""Hub: answer faster + catch plane questions worded with 'sky' / 'above'.

- TX_TAIL 2.0 -> 1.0 s: after the transmitter unkeys, wait 1 s (was 2 s)
  before processing the recording. Safe now because Stage 2's TXKEYED wait
  already confirms the transmission actually ended; this is only a backstop
  for the courtesy beep + squelch tail (~150 ms + tail).
- File-stability wait 3 -> 2 polls (1.5 s -> 1.0 s): the file only needs to
  stop growing for 1 s to be considered done, since TXKEYED already proved
  the speaker finished.
- Together these save ~1.5 s off every answer (round trip ~8-9 s -> ~6.5-7.5 s).
- ADS-B keywords: add "sky" and "above" to _plane_words so a question like
  "what's in the sky right now" or "what's above us" fetches the plane data.
  "sky" is safe; "above" is a bit broader but in radio context it almost
  always means "above us" (planes).
- Requires backup /home/asl/backups/20261122/ai_orchestrator.py to exist.
- Writes via temp file + py_compile + shutil.copyfile; aborts safely if any
  anchor is not found exactly once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_faster_sky.py"

if not os.path.isfile(BACKUP):
    print("PATCH ABORTED: backup %s not found; refusing to edit live file" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("TX_TAIL 2.0 -> 1.0 (post-unkey wait)",
     "TX_TAIL = 2.0",
     "TX_TAIL = 1.0"),
    ("File-stability wait 3 -> 2 polls (1.5s -> 1.0s)",
     "if stable_count >= 3",
     "if stable_count >= 2"),
    ("ADS-B keywords: add 'sky' and 'above'",
     '"kemp", "kcmo", "police")',
     '"kemp", "kcmo", "police", "sky", "above")'),
]

for what, old, new in EDITS:
    n = src.count(old)
    if n != 1:
        print("PATCH ABORTED: %s: expected exactly 1 occurrence, found %d" % (what, n))
        sys.exit(1)
    src = src.replace(old, new, 1)
    print("ok: " + what)

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
print("Restart the hub: sudo systemctl restart ai_orchestrator.service")
