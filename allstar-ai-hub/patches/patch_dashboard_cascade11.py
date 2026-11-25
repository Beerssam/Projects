#!/usr/bin/env python3
"""patch_dashboard_cascade11.py - AI Hub dashboard: stop the pool
panel wrapping (Nov 25 2026)

Sam's report on v10: the two-column squeeze runs the full height
of the panel, but the switch stack is only three rows tall - so
the model lines wrap mid-sentence ("3 used - ~17 left of / 20",
"3.5-flash-lite / NEXT") and the status line wraps too.

Restructure:
- The flex row now ends after the three short stat lines
  (ACTIVE KEY / RECENT REPLIES / LAST FAILOVER) beside the switch
  stack. Everything else - the model blocks, QUESTIONS TODAY, the
  WEB SEARCH status line - drops below the stack at full panel
  width.
- LAST FAILOVER shows just the time (HH:MM:SS) so it fits beside
  the stack on a phone; the full date + time stays on the Q&A
  entries, where Sam asked for it. (pool_api reads it through the
  repaired _log_time and keeps only the time part.)
- The model name line and the used/left line in the pollPool
  builder get white-space:nowrap, so they can never wrap again.

No other behavior changes: same ids, same painter, same APIs.

Safety: each anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_dashboard_cascade11.py
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

# --- The uniform switch stack, byte-identical to v10's ---
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

# --- Edit 1: close the flex row right after LAST FAILOVER ---
_FAIL = """    <div class="stat-line">LAST FAILOVER: <b id="pool-failover">...</b></div>"""

old_region = _FAIL
new_region = _FAIL + """
    </div>
""" + _STACK + """
    </div>"""

# --- Edit 2: remove the stack + closes from after the status line ---
_GROUND = """    <div class="stat-line" id="pool-grounding"></div>"""
old_ground = _GROUND + """
    </div>
""" + _STACK + """
    </div>"""

# --- Edit 3: model lines never wrap ---
old_render = """                    html += '<div style="margin:7px 0;"><div><b>' + name + '</b> ' + status + '</div><div class="stat-line">' + m.used + ' used &middot; ~' + m.left + ' left of ' + m.cap + '</div></div>';"""
new_render = """                    html += '<div style="margin:7px 0;"><div style="white-space:nowrap;"><b>' + name + '</b> ' + status + '</div><div class="stat-line" style="white-space:nowrap;">' + m.used + ' used &middot; ~' + m.left + ' left of ' + m.cap + '</div></div>';"""

# --- Edit 4: LAST FAILOVER keeps only the time part ---
old_failover = """            last_failover = _log_time(line) or "recent\""""
new_failover = """            last_failover = _log_time(line).rsplit(" ", 1)[-1] or "recent\""""

EDITS = [
    ("region", old_region, new_region),
    ("ground", old_ground, _GROUND),
    ("render", old_render, new_render),
    ("failover", old_failover, new_failover),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-cascade11"
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
