#!/usr/bin/env python3
"""patch_hub_prompt_scope.py - AI hub: stop the scope refusals
(Nov 25 2026)

Sam's on-air tests, Nov 25 09:41-09:43: three phrasings of the
president question, in DDG-only mode, Google-only mode, and both
engines on - all three answered with a refusal: "My functions are
limited to node status and local aircraft information."

Root cause: the system prompt introduces the model as "an AllStar
Link radio node assistant" and then talks almost entirely about
aircraft data and hub health. It never says the scope is a limit -
but it never says general questions are allowed either, and the
model infers a limit and refuses. (An ungrounded model would have
answered from memory; a refusal in all three engine modes is the
prompt, not the search machinery.)

Fix: one paragraph appended to the aircraft rule in GENERAL
RESPONSE RULES, stating that the assistant is general-purpose,
that general questions must be answered (using web search when
available for current facts), and that node status / aircraft data
are local sources, not limits - the exact refusal wording is
called out and forbidden.

Safety: the anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_hub_prompt_scope.py
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

old = "Never say you do not have access to live aircraft data when the repository is provided above."
new = (
    "Never say you do not have access to live aircraft data when the repository is provided above. "
    "You are also a general-purpose assistant, not only a node tool: when a caller asks a general question about the world "
    "(people, places, addresses, phone numbers, news, weather, public figures), answer it, and when web search is available "
    "to you, use it for current facts instead of relying on memory. Node status and aircraft data are your local sources, "
    "not limits on what you may answer. Never refuse a question by saying your functions are limited to node status or "
    "local aircraft information."
)

n = src.count(old)
if n != 1:
    print(f"ABORT: anchor found {n} times (need exactly 1). No changes made.")
    sys.exit(1)
if "You are also a general-purpose assistant" in src:
    print("ABORT: scope paragraph already present (patch already applied?). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-promptscope"
shutil.copy2(PATH, backup)
src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")
