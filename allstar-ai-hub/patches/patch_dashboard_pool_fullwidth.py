#!/usr/bin/env python3
"""Dashboard: make the GEMINI POOL box full-width.
Since the AI SERVICE panel moved out, the GEMINI POOL is the only item left
in the stat-grid, so on desktop it renders as a short half-width box in a
2-column grid with an empty right column. Unwrap it from the grid and drop
the `stat-box` class (which sets margin-bottom: 0 for grid items) so it
becomes a normal full-width `.panel` like the header, the map, and the Q&A
panel, with the standard 15px bottom margin.
Target: /home/asl/ai_dashboard.py with v3b + spacing patch applied.
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if the anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_pool_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

OLD = """<div class="stat-grid">

    <div class="panel stat-box">
        <div class="panel-title">GEMINI POOL</div>
        <div class="stat-line">ACTIVE KEY: <b id="pool-key">...</b></div>
        <div class="stat-line">RECENT REPLIES: <b id="pool-calls">...</b></div>
        <div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div>
    </div>
</div>"""

NEW = """<div class="panel">
    <div class="panel-title">GEMINI POOL</div>
    <div class="stat-line">ACTIVE KEY: <b id="pool-key">...</b></div>
    <div class="stat-line">RECENT REPLIES: <b id="pool-calls">...</b></div>
    <div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div>
</div>"""

EDITS = [
    ("GEMINI POOL: unwrap from stat-grid, full-width panel",
     OLD,
     NEW),
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
