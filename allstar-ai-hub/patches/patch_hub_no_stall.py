#!/usr/bin/env python3
"""patch_hub_no_stall.py - AI hub: forbid stall answers (Nov 25 2026)

Sam's on-air test, Nov 25 14:04: asked whether China King would be
open on Thanksgiving, the hub answered "I'm looking for China
King's Thanksgiving hours now." - and never came back. He had to
ask again ("Did you find anything?") to get the honest answer:
the search results do not show Thanksgiving hours.

The stall is a structural lie: the hub answers one question per
transmission and does no background work, so "I'm looking now"
promises a follow-up that can never happen. (Sam's own read was
right - a small restaurant's holiday hours most likely are not
published anywhere; the correct behavior is the second answer:
say so, in the same reply.)

Fix: one rule appended to the general-purpose paragraph added by
patch_hub_prompt_scope.py: never stall or promise a later answer;
answer in this reply from the information provided, and if it
does not cover the question, say plainly that the search results
do not show it.

Safety: the anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_hub_no_stall.py
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

old = "Never refuse a question by saying your functions are limited to node status or local aircraft information."
new = (
    "Never refuse a question by saying your functions are limited to node status or local aircraft information. "
    "Never stall or promise a later answer: you cannot look anything up after this reply, so never say you are looking, "
    "searching, or checking and will report back. Give the best answer you can in this reply from the information "
    "provided, and if that information does not cover the question, say plainly in this reply that your search "
    "results do not show it."
)

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)
if "Never stall or promise a later answer" in src:
    print("ABORT: no-stall rule already present (patch already applied?). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-nostall"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
