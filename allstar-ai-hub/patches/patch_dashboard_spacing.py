#!/usr/bin/env python3
"""Dashboard spacing fix: the AI SERVICE panel was moved out of the stat-grid
but kept the `stat-box` class, and `.stat-box { margin-bottom: 0 }` (needed
inside the grid, where the grid gap handles spacing) now kills its bottom
margin, so the gap below it does not match the other panels' 15px.
This drops `stat-box` from the AI SERVICE panel only (the GEMINI POOL panel
keeps it, still inside the grid), so it gets the standard `.panel`
margin-bottom: 15px like the header and the control buttons.
Target: /home/asl/ai_dashboard.py with v3b applied (AI SERVICE above the
control buttons).
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if the anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_spacing_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("AI SERVICE panel: drop stat-box class so it gets the standard panel margin",
     '    <div class="panel stat-box">\n        <div class="panel-title">AI SERVICE</div>',
     '    <div class="panel">\n        <div class="panel-title">AI SERVICE</div>'),
]

for desc, old, new in EDITS:
    n = src.count(old)
    if n != 1:
        print("PATCH ABORTED: %s: expected exactly 1 occurrence, found %d" % (desc, n))
        sys.exit(1)
    src = src.replace(old, new)
    print("ok: %s" % desc)

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
