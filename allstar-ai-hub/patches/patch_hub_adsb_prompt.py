#!/usr/bin/env python3
"""Hub: make Gemini actually use the ADS-B repository for aircraft questions.

Root cause (Nov 23, from the live ai_orchestrator.py): the ADS-B fetch works
and the repository block IS included in the system prompt when plane words are
present (verified: 21:45:58 fetch returned 19 aircraft, yet Gemini answered
"I do not have access to live aircraft data"). The data was in the prompt but
Gemini didn't use it -- most likely because "near me" is location-ambiguous
(Gemini doesn't know the caller is in Shawnee) and the aircraft instruction
was a single soft line.

Fix (1 edit): replace the soft aircraft rule with an explicit, forceful one --
ground the caller in Shawnee (so "near me"/"overhead"/"nearby"/"above" all mean
the repository area), state the repository IS the live aircraft data, and
forbid claiming no access when it is provided.
- Requires backup /home/asl/backups/20261122/ai_orchestrator.py.
- Writes via temp file + py_compile + shutil.copyfile; aborts safely if the
  anchor is missing.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_adsb_prompt.py"

if not os.path.isfile(BACKUP):
    print("PATCH ABORTED: backup %s not found; refusing to edit live file" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

old = '"If a human asks about overhead aircraft, use the airspace repository data provided above to answer concisely.\\n"'
new = '"The caller is at the hub in Shawnee, KS, so \'near me\', \'overhead\', \'nearby\' and \'above\' all mean the airspace repository area around Shawnee. If a human asks about aircraft, you MUST answer using the airspace repository data provided above -- that repository IS your live aircraft data. List the aircraft from it. Never say you do not have access to live aircraft data when the repository is provided above.\\n"'
if src.count(old) != 1:
    print("PATCH ABORTED: aircraft rule anchor: expected exactly 1 occurrence, found %d" % src.count(old))
    sys.exit(1)
src = src.replace(old, new, 1)
print("ok: aircraft rule strengthened (Shawnee grounding + must-use repository + never claim no access)")

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
print("Test: ask 'what aircraft are near me' -- she should list real aircraft from the repository, not say she has no access.")
print("Rollback: cp /home/asl/backups/20261122/ai_orchestrator.py /home/asl/ai_orchestrator.py && sudo systemctl restart ai_orchestrator.service")
