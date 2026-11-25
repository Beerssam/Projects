#!/usr/bin/env python3
"""patch_dashboard_cascade9.py - AI Hub dashboard: all three search
switches stacked in the panel's top-right corner (Nov 25 2026)

Placement fix. Sam's actual ask all along (clarified Nov 25 08:01):
the GOOGLE and DDG switches belong WITH the master WEB SEARCH switch
- stacked directly underneath it in the top-right corner of the
GEMINI POOL panel, labels uniform (DUCKDUCKGO shortened to DDG).
cascade5 placed the engine switches in the panel body under the
status line; cascade6/7/8 only polished that placement. This patch
moves them.

What changes:
- The panel title becomes a flex row: "GEMINI POOL" on the left, a
  right-aligned stack of three switch rows on the right:
      WEB SEARCH  [ switch ]
      GOOGLE      [ switch ]
      DDG         [ switch ]
  Each row is label + switch, right-aligned, so the three switches
  form one column. The stack is in normal flow (no floats), so the
  title area simply grows to fit it - no overlap with the stats.
- The two engine rows in the panel body are removed.
- The buttons themselves are byte-identical (same ids, onclick
  handlers, knob spans, sizes), so every toggle function and the
  painter work unchanged. The status line in the body is untouched.

Safety: each anchor must match exactly once or the patch aborts with
no changes; compiled in memory before writing; timestamped backup;
result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade9.py
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

_MASTER_BTN = """<button id="search-toggle" onclick="toggleSearch()" disabled title="Toggle web search" style="width:40px; height:20px; border-radius:10px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="search-knob" style="position:absolute; top:2px; left:2px; width:16px; height:16px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button>"""
_GOOGLE_BTN = """<button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style="display:inline-block; flex:0 0 auto; width:34px !important; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="google-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button>"""
_DDG_BTN = """<button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style="display:inline-block; flex:0 0 auto; width:34px !important; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="ddg-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button>"""

# --- Edit 1: the title gains the three-switch stack ---
old_title = """    <div class="panel-title">GEMINI POOL <span style="float:right; font-size:11px;">WEB SEARCH """ + _MASTER_BTN + """</span></div>"""
new_title = (
    """    <div class="panel-title" style="display:flex; justify-content:space-between; align-items:flex-start;">GEMINI POOL <span style="font-size:11px; text-align:right;">"""
    + """<span style="display:flex; align-items:center; justify-content:flex-end; gap:6px; margin-bottom:5px;">WEB SEARCH """
    + _MASTER_BTN
    + """</span><span style="display:flex; align-items:center; justify-content:flex-end; gap:6px; margin-bottom:5px;">GOOGLE """
    + _GOOGLE_BTN
    + """</span><span style="display:flex; align-items:center; justify-content:flex-end; gap:6px;">DDG """
    + _DDG_BTN
    + """</span></span></div>"""
)

# --- Edit 2 + 3: the engine rows leave the panel body ---
old_google = """    <div style="display:flex; align-items:center; margin-top:6px;"><span style="display:inline-block; flex:0 0 118px; width:118px;">GOOGLE</span>""" + _GOOGLE_BTN + """</div>
"""
old_ddg = """    <div style="display:flex; align-items:center; margin-top:4px;"><span style="display:inline-block; flex:0 0 118px; width:118px;">DUCKDUCKGO</span>""" + _DDG_BTN + """</div>
"""

EDITS = [
    ("title", old_title, new_title),
    ("google", old_google, ""),
    ("ddg", old_ddg, ""),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade9"
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
