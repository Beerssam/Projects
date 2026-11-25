#!/usr/bin/env python3
"""patch_dashboard_listen3.py - AI hub dashboard: Listen player
diagnostics (Nov 25 2026)

Sam's report, Nov 25 14:18: after the autoplay fix, Chrome still
plays nothing and the button STAYS on "Listening..." - it never
resets. That detail matters: if play() were rejecting, the listen2
code would reset the button. So the failure sits in a step the
player swallows silently: the clip-list fetch failing or returning
non-JSON through the proxy path Sam's browser uses, or the audio
file itself failing to load (the 'error' handler just drains the
queue without a word).

Rather than guess a third time, the player now reports its state
in a small status text beside the button:

  starting... / clip list OK (N clips) / playing <name>
  clip list failed (HTTP <status>) / clip list not JSON
  audio error <code> on <name> / blocked: <error name>

One tap tells us the exact failing step and, if it is the proxy,
which path is broken - then the fix is targeted instead of
speculative. Playback logic is otherwise unchanged (unlock,
queue, poll).

Safety: both anchors must match exactly once or the patch aborts
with no changes; an already-applied guard covers reruns; compiled
in memory before writing; timestamped backup; py_compile check.

Run with:  sudo python3 patch_dashboard_listen3.py
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

if "listen-status" in src:
    print("ABORT: listen diagnostics already present (patch already applied?). No changes made.")
    sys.exit(1)

# --- Edit 1: a status span beside the button ---
old_btn = '''            <button id="listen-btn" title="Listen to the hub: callers and the AI, listen-only" style="width:auto; padding:8px 14px; border-radius:20px; border:1px solid #30363d; background:#21262d; color:#e6edf3; cursor:pointer; font-size:0.9rem;">🔊 Listen</button>'''
new_btn = '''            <button id="listen-btn" title="Listen to the hub: callers and the AI, listen-only" style="width:auto; padding:8px 14px; border-radius:20px; border:1px solid #30363d; background:#21262d; color:#e6edf3; cursor:pointer; font-size:0.9rem;">🔊 Listen</button>
            <span id="listen-status" style="font-size:0.8rem; color:#8b949e;"></span>'''

# --- Edit 2: the player script, now with a voice ---
old_script = '''<script>
(function () {
    var btn = document.getElementById('listen-btn');
    if (!btn) return;
    var audio = new Audio();
    var on = false, timer = null, playing = false;
    var queue = [], seen = {};
    function playNext() {
        if (!on || playing || !queue.length) return;
        var item = queue.shift();
        playing = true;
        audio.src = '/api/listen/' + encodeURIComponent(item.name);
        var p = audio.play();
        if (p && p.catch) p.catch(function () {
            playing = false;
            if (timer) clearInterval(timer);
            on = false;
            btn.textContent = '🔊 Listen';
            btn.style.background = '#21262d';
            btn.title = 'Chrome blocked audio playback - tap Listen again';
        });
    }
    audio.addEventListener('ended', function () { playing = false; playNext(); });
    audio.addEventListener('error', function () { playing = false; playNext(); });
    function poll() {
        fetch('/api/listen').then(function (r) { return r.json(); }).then(function (d) {
            (d.clips || []).forEach(function (c) {
                if (!seen[c.name]) { seen[c.name] = 1; queue.push(c); }
            });
            queue.sort(function (a, b) { return a.mtime - b.mtime; });
            while (queue.length > 10) queue.shift();
            playNext();
        }).catch(function () {});
    }
    btn.addEventListener('click', function () {
        on = !on;
        btn.textContent = on ? '🔊 Listening…' : '🔊 Listen';
        btn.style.background = on ? '#1f6feb' : '#21262d';
        if (on) {
            // Unlock: play a silent clip synchronously inside the tap so
            // Chrome marks this element user-activated and lets the real
            // clips play when they arrive.
            audio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            var _up = audio.play();
            if (_up && _up.catch) _up.catch(function () {});
            queue = []; seen = {};
            fetch('/api/listen').then(function (r) { return r.json(); }).then(function (d) {
                var clips = d.clips || [];
                clips.forEach(function (c) { seen[c.name] = 1; });
                if (clips.length) {
                    queue = [clips[clips.length - 1]];
                    playNext();
                }
            }).catch(function () {});
            timer = setInterval(poll, 3000);
        } else {
            if (timer) clearInterval(timer);
            queue = []; playing = false;
            audio.pause();
        }
    });
})();
</script>'''

new_script = '''<script>
(function () {
    var btn = document.getElementById('listen-btn');
    if (!btn) return;
    var statusEl = document.getElementById('listen-status');
    function say(msg) { if (statusEl) statusEl.textContent = msg; }
    var audio = new Audio();
    var on = false, timer = null, playing = false;
    var queue = [], seen = {};
    var currentName = '';
    function stopWith(msg) {
        if (timer) clearInterval(timer);
        on = false; playing = false; queue = [];
        btn.textContent = '🔊 Listen';
        btn.style.background = '#21262d';
        say(msg);
    }
    function playNext() {
        if (!on || playing || !queue.length) return;
        var item = queue.shift();
        playing = true;
        currentName = item.name;
        say('playing ' + item.name);
        audio.src = '/api/listen/' + encodeURIComponent(item.name);
        var p = audio.play();
        if (p && p.catch) p.catch(function (e) {
            stopWith('blocked: ' + (e && e.name ? e.name : 'play failed'));
        });
    }
    audio.addEventListener('ended', function () { playing = false; playNext(); });
    audio.addEventListener('error', function () {
        var code = (audio.error && audio.error.code) ? audio.error.code : '?';
        playing = false;
        if (on) say('audio error ' + code + ' on ' + currentName);
        playNext();
    });
    function fetchClips() {
        return fetch('/api/listen', { cache: 'no-store' }).then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.text();
        }).then(function (t) {
            try { return JSON.parse(t); }
            catch (e) { throw new Error('clip list not JSON'); }
        });
    }
    function poll() {
        fetchClips().then(function (d) {
            (d.clips || []).forEach(function (c) {
                if (!seen[c.name]) { seen[c.name] = 1; queue.push(c); }
            });
            queue.sort(function (a, b) { return a.mtime - b.mtime; });
            while (queue.length > 10) queue.shift();
            playNext();
        }).catch(function (e) { say('clip list failed (' + e.message + ')'); });
    }
    btn.addEventListener('click', function () {
        on = !on;
        if (on) {
            btn.textContent = '🔊 Listening…';
            btn.style.background = '#1f6feb';
            say('starting…');
            // Unlock: play a silent clip synchronously inside the tap so
            // Chrome marks this element user-activated and lets the real
            // clips play when they arrive.
            audio.src = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
            var _up = audio.play();
            if (_up && _up.catch) _up.catch(function () {});
            queue = []; seen = {};
            fetchClips().then(function (d) {
                var clips = d.clips || [];
                clips.forEach(function (c) { seen[c.name] = 1; });
                say('clip list OK (' + clips.length + ' clips)');
                if (clips.length) {
                    queue = [clips[clips.length - 1]];
                    playNext();
                }
            }).catch(function (e) { say('clip list failed (' + e.message + ')'); });
            timer = setInterval(poll, 3000);
        } else {
            if (timer) clearInterval(timer);
            queue = []; playing = false;
            audio.pause();
            btn.textContent = '🔊 Listen';
            btn.style.background = '#21262d';
            say('');
        }
    });
})();
</script>'''

EDITS = [
    ("button", old_btn, new_btn),
    ("script", old_script, new_script),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-listen3"
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
