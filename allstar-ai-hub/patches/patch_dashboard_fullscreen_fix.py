#!/usr/bin/env python3
"""Dashboard: fix the fullscreen buttons and fit.
Sam's feedback: the Full screen / Exit buttons were full-width bars (the
dashboard's global `button { width: 100% }` rule was stretching them), and
fullscreen did not quite fill the screen.
- Fullscreen button is now just the ⛶ icon, small, bottom-right corner of
  the map, semi-transparent (see-through) with a faint border.
- Exit button is now just an X, small, top-right corner when fullscreen,
  semi-transparent the same way.
- The fullscreen button hides while fullscreen is on (it was still showing
  at the bottom); it comes back when you exit.
- Fullscreen now uses inset: 0 + 100dvh so it fills the viewport on mobile
  and desktop in either orientation, and the map re-fits on rotate/resize.
Target: /home/asl/ai_dashboard.py with the fullscreen patch applied.
Backup required: /home/asl/backups/20261123/ai_dashboard.py.
Aborts safely if any anchor is missing or appears more than once.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_fullscreen_fix_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

EDITS = [
    ("CSS: fullscreen fit (inset + dvh, no panel constraints)",
     ".map-fullscreen { position: fixed !important; top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important; width: 100vw !important; height: 100vh !important; height: 100dvh !important; z-index: 1000 !important; border-radius: 0 !important; margin: 0 !important; }",
     ".map-fullscreen { position: fixed !important; inset: 0 !important; width: 100vw !important; width: 100dvw !important; height: 100vh !important; height: 100dvh !important; z-index: 1000 !important; border-radius: 0 !important; margin: 0 !important; padding: 0 !important; border: none !important; }"),
    ("CSS: fullscreen button -> small transparent icon, bottom-right",
     ".map-fs-btn { position: absolute; right: 10px; bottom: 24px; z-index: 1001; background: rgba(13,17,23,0.92); color: #e6edf3; border: 1px solid #58a6ff; border-radius: 6px; padding: 8px 12px; font-size: 13px; font-weight: 700; cursor: pointer; }",
     ".map-fs-btn { position: absolute !important; right: 10px !important; bottom: 10px !important; z-index: 1001 !important; width: auto !important; min-width: 0 !important; display: flex !important; align-items: center !important; justify-content: center !important; background: rgba(13,17,23,0.55) !important; color: #e6edf3 !important; border: 1px solid rgba(230,237,243,0.35) !important; border-radius: 6px !important; padding: 6px 9px !important; font-size: 18px !important; line-height: 1 !important; font-weight: 700 !important; cursor: pointer !important; }"),
    ("CSS: exit button -> small transparent X, top-right",
     ".map-fs-exit { position: fixed; right: 12px; top: 12px; z-index: 1002; background: rgba(13,17,23,0.92); color: #e6edf3; border: 1px solid #f85149; border-radius: 6px; padding: 8px 12px; font-size: 13px; font-weight: 700; cursor: pointer; display: none; }",
     ".map-fs-exit { position: fixed !important; right: 10px !important; top: 10px !important; z-index: 1002 !important; width: auto !important; min-width: 0 !important; display: none !important; align-items: center !important; justify-content: center !important; background: rgba(13,17,23,0.55) !important; color: #e6edf3 !important; border: 1px solid rgba(230,237,243,0.35) !important; border-radius: 6px !important; padding: 6px 10px !important; font-size: 18px !important; line-height: 1 !important; font-weight: 700 !important; cursor: pointer !important; }\n.map-fs-exit.map-fs-show { display: flex !important; }"),
    ("JS: fullscreen button is just the icon; hide it while fullscreen",
     "fsBtn.className = 'map-fs-btn'; fsBtn.textContent = '⛶ Full screen';",
     "fsBtn.className = 'map-fs-btn'; fsBtn.textContent = '⛶'; fsBtn.title = 'Full screen';"),
    ("JS: enter fullscreen hides the button, shows X, refits on rotate",
     "fsBtn.onclick = function(){ var m = document.getElementById('map'); m.classList.add('map-fullscreen'); document.getElementById('map-fs-exit').style.display = 'block'; setTimeout(function(){ adsbMap.invalidateSize(); }, 50); };",
     "fsBtn.onclick = function(){ var m = document.getElementById('map'); m.classList.add('map-fullscreen'); fsBtn.style.display = 'none'; document.getElementById('map-fs-exit').classList.add('map-fs-show'); setTimeout(function(){ adsbMap.invalidateSize(); }, 60); };"),
    ("JS: exit button is just an X",
     "fsExit.id = 'map-fs-exit'; fsExit.className = 'map-fs-exit'; fsExit.textContent = '✕ Exit full screen';",
     "fsExit.id = 'map-fs-exit'; fsExit.className = 'map-fs-exit'; fsExit.textContent = '✕'; fsExit.title = 'Exit full screen';"),
    ("JS: exit restores the button and refits on rotate",
     "fsExit.onclick = function(){ var m = document.getElementById('map'); m.classList.remove('map-fullscreen'); fsExit.style.display = 'none'; setTimeout(function(){ adsbMap.invalidateSize(); }, 50); };",
     "fsExit.onclick = function(){ var m = document.getElementById('map'); m.classList.remove('map-fullscreen'); fsExit.classList.remove('map-fs-show'); fsBtn.style.display = 'flex'; setTimeout(function(){ adsbMap.invalidateSize(); }, 60); };\n    window.addEventListener('resize', function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } });\n    window.addEventListener('orientationchange', function(){ setTimeout(function(){ if (document.getElementById('map').classList.contains('map-fullscreen')) { adsbMap.invalidateSize(); } }, 200); });"),
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
