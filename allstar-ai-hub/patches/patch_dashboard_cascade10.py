#!/usr/bin/env python3
"""patch_dashboard_cascade10.py - AI Hub dashboard: two-column pool
panel, uniform switches, Q&A date+time (Nov 25 2026)

Three changes, all requested by Sam on Nov 25:

1. FILL THE DEAD SPACE. The v9 switch stack made the panel title
   three rows tall, leaving empty panel under "GEMINI POOL". The
   title goes back to a plain one-liner, and everything that was
   below it (ACTIVE KEY / RECENT REPLIES / LAST FAILOVER, the model
   blocks, QUESTIONS TODAY, the WEB SEARCH status line) now flows
   in a left column BESIDE the switch stack: one flex row, content
   column flex:1, switch column fixed on the right.

2. UNIFORM SWITCHES. The master was 40x20 with a 16px knob; the
   engine switches were 34x18 with 14px knobs. All three are now
   the same 40x20 pill with a 16px knob, and the painter's knob
   travel for GOOGLE/DDG moves from 18px to 22px to match.

3. DATE + TIME ON Q&A ENTRIES. The Q&A renderer already prints
   it.time over every question, and recent_api already collects it
   via _log_time - but _log_time's pattern is bracket-anchored to
   the pre-Nov-24 "[HH:MM:SS" format, so it returns "" for the
   current "[YYYY-MM-DD HH:MM:SS.mmm]" stamps. The helper now
   tries the dated format first and returns "YYYY-MM-DD HH:MM:SS",
   falling back to the old bare-time format for old log lines.
   This also repairs pool_api's LAST FAILOVER, which reads through
   the same helper.

Safety: each anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade10.py
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

# --- The v9 title, byte for byte (anchors for Edit 1) ---
_M_BTN = """<button id="search-toggle" onclick="toggleSearch()" disabled title="Toggle web search" style="width:40px; height:20px; border-radius:10px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="search-knob" style="position:absolute; top:2px; left:2px; width:16px; height:16px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button>"""
_G_BTN = """<button id="google-toggle" onclick="toggleGoogle()" disabled title="Toggle Google search" style="display:inline-block; flex:0 0 auto; width:34px !important; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="google-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button>"""
_D_BTN = """<button id="ddg-toggle" onclick="toggleDdg()" disabled title="Toggle DuckDuckGo search" style="display:inline-block; flex:0 0 auto; width:34px !important; height:18px; border-radius:9px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;"><span id="ddg-knob" style="position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#e6edf3; transition:left 0.15s;"></span></button>"""

old_title = (
    """    <div class="panel-title" style="display:flex; justify-content:space-between; align-items:flex-start;">GEMINI POOL <span style="font-size:11px; text-align:right;">"""
    + """<span style="display:flex; align-items:center; justify-content:flex-end; gap:6px; margin-bottom:5px;">WEB SEARCH """
    + _M_BTN
    + """</span><span style="display:flex; align-items:center; justify-content:flex-end; gap:6px; margin-bottom:5px;">GOOGLE """
    + _G_BTN
    + """</span><span style="display:flex; align-items:center; justify-content:flex-end; gap:6px;">DDG """
    + _D_BTN
    + """</span></span></div>"""
)
new_title = (
    """    <div class="panel-title">GEMINI POOL</div>
    <div style="display:flex; gap:14px; align-items:flex-start;">
    <div style="flex:1; min-width:0;">"""
)

# --- The uniform switch stack (inserted by Edit 2) ---
_UBTN = 'display:inline-block; flex:0 0 auto; width:40px !important; height:20px; border-radius:10px; border:none; background:#484f58; position:relative; vertical-align:middle; opacity:0.45; padding:0; cursor:pointer;'
_UKNOB = 'position:absolute; top:2px; left:2px; width:16px; height:16px; border-radius:50%; background:#e6edf3; transition:left 0.15s;'


def _ubtn(bid, fn, title, knob):
    return (
        '<button id="' + bid + '" onclick="' + fn + '" disabled title="' + title
        + '" style="' + _UBTN + '"><span id="' + knob + '" style="' + _UKNOB
        + '"></span></button>'
    )


_STACK = (
    """    <div style="font-size:11px; text-align:right; flex:0 0 auto;">
    <div style="display:flex; align-items:center; justify-content:flex-end; gap:6px; margin-bottom:5px;">WEB SEARCH """
    + _ubtn("search-toggle", "toggleSearch()", "Toggle web search", "search-knob")
    + """</div>
    <div style="display:flex; align-items:center; justify-content:flex-end; gap:6px; margin-bottom:5px;">GOOGLE """
    + _ubtn("google-toggle", "toggleGoogle()", "Toggle Google search", "google-knob")
    + """</div>
    <div style="display:flex; align-items:center; justify-content:flex-end; gap:6px;">DDG """
    + _ubtn("ddg-toggle", "toggleDdg()", "Toggle DuckDuckGo search", "ddg-knob")
    + """</div>
    </div>"""
)

old_ground = """    <div class="stat-line" id="pool-grounding"></div>"""
new_ground = old_ground + """
    </div>
""" + _STACK + """
    </div>"""

# --- _log_time repair (Edit 3) ---
old_logtime = '''def _log_time(line):
    m = re.search(r'\\[(\\d{2}:\\d{2}:\\d{2})', line)
    return m.group(1) if m else ""'''
new_logtime = '''def _log_time(line):
    m = re.search(r'\\[(\\d{4}-\\d{2}-\\d{2}) (\\d{2}:\\d{2}:\\d{2})', line)
    if m:
        return m.group(1) + " " + m.group(2)
    m = re.search(r'\\[(\\d{2}:\\d{2}:\\d{2})', line)
    return m.group(1) if m else ""'''

EDITS = [
    ("title", old_title, new_title),
    ("stack", old_ground, new_ground),
    ("logtime", old_logtime, new_logtime),
    ("gk", "paint('google-toggle', 'google-knob', window._googleEnabled !== false, '18px');", "paint('google-toggle', 'google-knob', window._googleEnabled !== false, '22px');"),
    ("dk", "paint('ddg-toggle', 'ddg-knob', window._ddgEnabled !== false, '18px');", "paint('ddg-toggle', 'ddg-knob', window._ddgEnabled !== false, '22px');"),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade10"
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
