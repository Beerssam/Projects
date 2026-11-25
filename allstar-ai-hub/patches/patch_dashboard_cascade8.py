#!/usr/bin/env python3
"""patch_dashboard_cascade8.py - AI Hub dashboard: engine switches in a
flex row (Nov 25 2026)

Layout fix, third pass - and the last guess. What the screenshots prove
(Sam, Nov 25 ~06:03 and ~06:07 CST):

  - GOOGLE label on one line, its switch on the next line, hard left.
  - DUCKDUCKGO label on one line, its switch on the next line, hard left.
  - The master WEB SEARCH switch stacks the same way under its label
    in the panel-title corner - so this is not specific to the engine
    rows, it is how this dashboard lays out buttons.

What the two missed fixes prove:

  - cascade6 (fixed-width inline-block label, button untouched) did
    not move the switch up beside the label.
  - cascade7 (display:inline-block on the buttons, inline style)
    also did not move it, even though Sam applied it (PATCH OK),
    restarted ai_dashboard, and refreshed in incognito (cache ruled
    out, and grep -c 'width:118px' = 2 proved v6 was in the file).

An inline display:inline-block loses only to a stylesheet rule with
!important, or to some other rule that forces the break. Guessing
which rule for a third time is how v6 and v7 were built. This patch
stops guessing: it replaces each engine row with a flex row.

  - The row div itself is display:flex (inline style, and it drops
    the .stat-line class, so no .stat-line rule can restyle it).
  - Flex items sit in a row whatever their own display value is:
    even a button forced to display:block (!important or not) is
    laid out horizontally as a flex item. That is the mechanism
    v6/v7 could not use.
  - The label keeps its 118px column (flex:0 0 118px) so both
    switches line up in one vertical column, as Sam asked.
  - The button keeps width:34px, now with !important, so a
    full-width button rule in the stylesheet cannot stretch it
    across the row either. (The master switch renders at its own
    40px, so no such width rule is expected - this is insurance,
    not a guess about the cause.)

Result, if it works as designed:

    GOOGLE      [ switch ]
    DUCKDUCKGO  [ switch ]

No behavior changes: same button ids, onclick handlers, knob spans,
and the same toggle functions. If this still does not line up, the
next step is NOT another layout patch - it is Sam pasting the
stylesheet rules (the grep the main chat already asked for at
06:13 CST), because something outside this panel's own markup
would then be at work.

Safety: each anchor must match exactly once or the patch aborts with
no changes; compiled in memory before writing; timestamped backup;
result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade8.py
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

_BTN = 'display:inline-block; flex:0 0 auto; width:34px !important; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;'
_KNOB = 'position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;'

old_google = """    <div class="stat-line" style="margin-top:6px;"><span style="display:inline-block; width:118px;">GOOGLE</span><button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style="display:inline-block; width:34px; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="google-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button></div>"""

new_google = (
    """    <div style="display:flex; align-items:center; margin-top:6px;"><span style="display:inline-block; flex:0 0 118px; width:118px;">GOOGLE</span><button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style=\""""
    + _BTN
    + """\"><span id="google-knob" style=\""""
    + _KNOB
    + """\"></span></button></div>"""
)

old_ddg = """    <div class="stat-line" style="margin-top:4px;"><span style="display:inline-block; width:118px;">DUCKDUCKGO</span><button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style="display:inline-block; width:34px; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="ddg-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button></div>"""

new_ddg = (
    """    <div style="display:flex; align-items:center; margin-top:4px;"><span style="display:inline-block; flex:0 0 118px; width:118px;">DUCKDUCKGO</span><button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style=\""""
    + _BTN
    + """\"><span id="ddg-knob" style=\""""
    + _KNOB
    + """\"></span></button></div>"""
)

EDITS = [
    ("google", old_google, new_google),
    ("ddg", old_ddg, new_ddg),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade8"
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
