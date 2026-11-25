#!/usr/bin/env python3
"""patch_hub_honest_search.py - AI hub: only claim search results
that were actually provided for this question (Nov 25 2026)

Sam's test, Nov 25 17:22: the follow-up "At Shawnee Mission Park,
do they have any designated remote control plane flying areas?"
contained no search trigger words, so no search ran for it - yet
the hub answered "My search results do not show any designated
remote control plane flying areas at Shawnee Mission Park." It
was reusing the PREVIOUS questions' searches (which ride in the
conversation memory) and borrowing their authority for a question
it never searched. From the operator's chair that reads as a
search that happened; it did not.

Fix: one rule appended to the same prompt paragraph as the
no-stall rule (patch_hub_no_stall.py): refer to search results
only when results were actually provided for THIS question; if
none were provided, answer without claiming or implying a search.

Safety: the anchor must match exactly once or the patch aborts
with no changes; an already-applied guard covers reruns; compiled
in memory before writing; timestamped backup; py_compile check.

Run with:  sudo python3 patch_hub_honest_search.py
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

old = "say plainly in this reply that your search results do not show it."
new = (
    "say plainly in this reply that your search results do not show it. "
    "Only refer to search results when search results were actually provided for this question. "
    "If no search results were provided for this question, answer from what you know without "
    "saying or implying that you searched."
)

if "Only refer to search results when" in src:
    print("ABORT: honesty rule already present (patch already applied?). No changes made.")
    sys.exit(1)

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-honestsearch"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
