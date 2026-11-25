#!/usr/bin/env python3
"""patch_dashboard_cascade7.py - AI Hub dashboard: engine switches
must be inline-block (Nov 25 2026)

Layout fix, second pass. cascade6 gave the GOOGLE / DUCKDUCKGO rows a
fixed-width inline-block label, but the switches still dropped onto
their own line under the label. Cause: the dashboard's stylesheet
styles buttons as block-level (the big control-panel buttons), and a
bare <button> inherits that; the switches' inline styles set size and
position but never display, so each one took a full row. The master
switch in the panel title only escaped this because its floated
wrapper shrink-wraps around it.

Fix: display:inline-block on both engine switch buttons, inline,
where it outranks the stylesheet. Nothing else changes.

Safety: each anchor must match exactly once or the patch aborts with
no changes; compiled in memory before writing; timestamped backup;
result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade7.py
Then:      sudo systemctl restart ai_dashboard
Rollback: copy the backup back over ai_dashboard.py and restart.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_dashboard.py"

with open(PATH) as f:
    src = f.read()

old_google = """<button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style="width:34px;"""
new_google = """<button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style="display:inline-block; width:34px;"""

old_ddg = """<button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style="width:34px;"""
new_ddg = """<button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style="display:inline-block; width:34px;"""

EDITS = [
    ("google", old_google, new_google),
    ("ddg", old_ddg, new_ddg),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade7"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_dashboard")
