#!/usr/bin/env python3
"""Raise the Gemini timeout back to 25s (AllStar AI hub, /home/asl/ai_orchestrator.py).

WHY:
  Stage 1 cut the Gemini timeout from 25s to 10s so a hung call would fail
  faster. But the API sometimes takes ~9s to answer (the 10:58 call took
  9.4s), so 10s leaves almost no headroom. On Nov 23 at 11:00 all four
  keys timed out in a row (~11.6s each = 10s timeout + 1.5s sleep) and
  the hub answered "System notice. Full pool exhaustion." even though
  the keys are fine and the API had answered 2 minutes earlier.

  The timeout is a MAXIMUM wait, not a fixed delay: a fast reply (3s)
  still comes back in 3s. Raising it only gives slow replies more time
  before the hub gives up. Restoring the original 25s (the value the hub
  ran on for months before Stage 1) is the safe, known-good choice.

  NOTE: the first version of this patch aborted because 'timeout=10'
  appears TWICE in the file. The other one is line 269, the AMI socket
  connect timeout (127.0.0.1:5038) — NOT Gemini, and it stays at 10s.
  This version targets ONLY the Gemini POST line (line 353), identified
  by 'requests.post'.

CHANGE (1 edit):
  Gemini POST timeout: 10 -> 25 seconds. The AMI socket timeout is untouched.

SAFETY:
- Refuses to run unless the verified backup exists at
  /home/asl/backups/20261122/ai_orchestrator.py
- The edit asserts the Gemini POST line exists exactly once and contains
  timeout=10; if the check fails, NOTHING is written.
- Writes to a temp file, syntax-checks it with py_compile, and only then
  copies it into place (shutil.copyfile, so it works across filesystems).
- Rollback: cp /home/asl/backups/20261122/ai_orchestrator.py \
               /home/asl/ai_orchestrator.py
            sudo systemctl restart ai_orchestrator.service

Run as root (or with sudo):  sudo python3 patch_timeout_25b.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_timeout_fix2.py"


def fail(msg):
    print("PATCH ABORTED: " + msg)
    sys.exit(1)


def main():
    if not os.path.exists(BACKUP):
        fail("verified backup not found at " + BACKUP + "; refusing to change anything.")
    with open(TARGET) as f:
        lines = f.readlines()

    # Find the Gemini POST line (the only requests.post in the file).
    hits = [i for i, ln in enumerate(lines) if "requests.post" in ln]
    if len(hits) != 1:
        fail("expected exactly 1 line containing 'requests.post', found %d" % len(hits))
    i = hits[0]
    if "timeout=10" not in lines[i]:
        fail("the requests.post line does not contain 'timeout=10'; refusing to change anything.")
    lines[i] = lines[i].replace("timeout=10", "timeout=25", 1)
    print("  ok: Gemini timeout 10 -> 25 (line %d)" % (i + 1))

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()
