#!/usr/bin/env python3
"""patch_dashboard_cascade6.py - AI Hub dashboard: line up the engine
switches (Nov 25 2026)

Layout fix only. The cascade5 engine switches sat in one flowing line
(GOOGLE <switch> DUCKDUCKGO <switch>); on a phone-width panel the line
wrapped mid-pair and the two switches landed ragged. They now get one
row each with a fixed-width label column, so both switches line up in
a clean vertical column:

    GOOGLE      [ switch ]
    DUCKDUCKGO  [ switch ]

No behavior changes. Safety: the anchor must match exactly once or
the patch aborts with no changes; compiled in memory before writing;
timestamped backup; result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade6.py
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

_BTN = 'width:34px; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;'
_KNOB = 'position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;'

old_html = """    <div class="stat-line" style="margin-top:6px;">GOOGLE <button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style="width:34px; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="google-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button> &nbsp; DUCKDUCKGO <button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style="width:34px; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="ddg-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button></div>"""

new_html = (
    """    <div class="stat-line" style="margin-top:6px;"><span style="display:inline-block; width:118px;">GOOGLE</span><button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style=\""""
    + _BTN
    + """\"><span id="google-knob" style=\""""
    + _KNOB
    + """\"></span></button></div>
    <div class="stat-line" style="margin-top:4px;"><span style="display:inline-block; width:118px;">DUCKDUCKGO</span><button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style=\""""
    + _BTN
    + """\"><span id="ddg-knob" style=\""""
    + _KNOB
    + """\"></span></button></div>"""
)

n = src.count(old_html)
if n != 1:
    print(f"ABORT: anchor 'html' found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade6"
shutil.copy2(PATH, backup)

src = src.replace(old_html, new_html)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_dashboard")
