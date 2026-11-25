#!/usr/bin/env python3
"""patch_dashboard_listen2.py - AI hub dashboard: Listen autoplay
fix (Nov 25 2026)

Sam's report, Nov 25 14:06: in Chrome the Listen button switches
to "Listening..." but no audio ever plays. Server side is proven
good: /api/listen serves the clips and they are plain PCM WAV
(16-bit mono 8 kHz - the format check Sam ran: "Microsoft PCM"),
which Chrome plays natively.

The failure is Chrome's autoplay policy: the player called play()
from inside a fetch() callback, and Chrome can refuse playback
that is not unlocked by the tap itself - the promise rejects, the
old code swallowed the rejection, marked the clip played, and
every later clip went the same way. Silence, with the button
cheerfully saying "Listening...".

Two changes to the listen script:

1. Unlock: the click handler now plays a tiny silent WAV on the
   shared audio element SYNCHRONOUSLY inside the tap, before any
   fetch. That marks the element as user-activated, so the real
   clips' play() calls afterwards are allowed.

2. Feedback: if a real clip's play() still rejects, the player
   stops cleanly (polling off, button back to "Listen") and the
   button's tooltip says Chrome blocked it - never silent again.

Safety: every anchor must match exactly once or the patch aborts
with no changes; an already-applied guard covers reruns; compiled
in memory before writing; timestamped backup; py_compile check.

Run with:  sudo python3 patch_dashboard_listen2.py
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

if "user-activated" in src or "audio blocked" in src:
    print("ABORT: autoplay fix already present (patch already applied?). No changes made.")
    sys.exit(1)

# --- Edit 1: surface play() rejections instead of swallowing them ---
old_play = '''        var p = audio.play();
        if (p && p.catch) p.catch(function () { playing = false; });'''
new_play = '''        var p = audio.play();
        if (p && p.catch) p.catch(function () {
            playing = false;
            if (timer) clearInterval(timer);
            on = false;
            btn.textContent = '🔊 Listen';
            btn.style.background = '#21262d';
            btn.title = 'Chrome blocked audio playback - tap Listen again';
        });'''

# --- Edit 2: unlock the audio element inside the tap itself ---
old_click = '''    btn.addEventListener('click', function () {
        on = !on;
        btn.textContent = on ? '🔊 Listening…' : '🔊 Listen';
        btn.style.background = on ? '#1f6feb' : '#21262d';
        if (on) {'''
new_click = '''    btn.addEventListener('click', function () {
        on = !on;
        btn.textContent = on ? '🔊 Listening…' : '🔊 Listen';
        btn.style.background = on ? '#1f6feb' : '#21262d';
        if (on) {
            // Unlock: play a silent clip synchronously inside the tap so
            // Chrome marks this element user-activated and lets the real
            // clips play when they arrive.
            audio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            var _up = audio.play();
            if (_up && _up.catch) _up.catch(function () {});'''

EDITS = [
    ("play", old_play, new_play),
    ("click", old_click, new_click),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-listen2"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

# Compile in memory BEFORE writing.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_dashboard")
