#!/usr/bin/env python3
"""patch_dashboard_listen.py - AI hub dashboard: Listen button
(Nov 25 2026)

Sam's request: a Listen button at the top right of the dashboard
that plays what the AI hub says - and, he added, what it HEARS, so
a visitor (or Sam) can follow both sides of a conversation and
judge incoming audio quality. Strictly listen-only: no microphone,
no transmit, no controls.

One feed covers both directions: Asterisk's monitor folder for the
hub node (/var/spool/asterisk/monitor/625731) already records every
transmission on the node as its own WAV clip - callers keying up,
the AI's spoken replies, and the 10-minute FCC ID beacons (Sam
explicitly wants the beacons included: "I like that it plays what
it says"). This is the same folder the orchestrator watches; no
orchestrator changes are needed.

Server side: GET /api/listen returns the newest settled clips
(mtime at least 2 s old, so a clip still being recorded is never
served) as JSON; GET /api/listen/<name> serves one clip's bytes
(name must be a bare .wav filename - no path traversal).

Page side: a Listen button in the header, right of the LIVE
TELEMETRY status. Clicking it plays the newest clip immediately
(instant confirmation), then polls every 3 s and plays new clips
in order. Clicking again stops. The button carries full inline
styles because the page's global button rule (width:100%, flex)
would otherwise stretch it across the header - the v6-v8 lesson.

Safety: every anchor must match exactly once or the patch aborts
with no changes; compiled in memory before writing; timestamped
backup; result must py_compile.

Run with:  sudo python3 patch_dashboard_listen.py
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

# All three anchors survive their replacements, so guard explicitly:
# a rerun must abort instead of duplicating routes and buttons.
if "listen_api" in src or "listen-btn" in src:
    print("ABORT: Listen feature already present - patch already applied. No changes made.")
    sys.exit(1)

# --- Edit 1: the two listen routes, before the ai_status route ---
old_route = '''@app.route('/api/ai_status')'''
new_route = '''LISTEN_DIR = "/var/spool/asterisk/monitor/625731"

@app.route('/api/listen')
def listen_api():
    _clips = []
    try:
        for _n in os.listdir(LISTEN_DIR):
            if _n.endswith(".wav"):
                try:
                    _mt = os.path.getmtime(os.path.join(LISTEN_DIR, _n))
                except Exception:
                    continue
                if _mt <= time.time() - 2:
                    _clips.append({"name": _n, "mtime": _mt})
    except Exception:
        pass
    _clips.sort(key=lambda c: c["mtime"])
    return json.dumps({"clips": _clips[-20:]})

@app.route('/api/listen/<name>')
def listen_audio(name):
    if "/" in name or not name.endswith(".wav"):
        return "", 404
    _p = os.path.join(LISTEN_DIR, name)
    if not os.path.isfile(_p):
        return "", 404
    try:
        with open(_p, "rb") as _f:
            _data = _f.read()
    except Exception:
        return "", 404
    return _data, 200, {"Content-Type": "audio/wav"}

@app.route('/api/ai_status')'''

# --- Edit 2: the button, grouped with the LIVE status at top right ---
old_status = '''        <div class="status">● LIVE TELEMETRY STREAMING</div>'''
new_status = '''        <div style="display:flex; align-items:center; gap:10px;">
            <div class="status">● LIVE TELEMETRY STREAMING</div>
            <button id="listen-btn" title="Listen to the hub: callers and the AI, listen-only" style="width:auto; padding:8px 14px; border-radius:20px; border:1px solid #30363d; background:#21262d; color:#e6edf3; cursor:pointer; font-size:0.9rem;">🔊 Listen</button>
        </div>'''

# --- Edit 3: the poll-and-play script, right after the header ---
old_header_end = '''    </header>'''
new_header_end = '''    </header>
<script>
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
        if (p && p.catch) p.catch(function () { playing = false; });
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

EDITS = [
    ("route", old_route, new_route),
    ("status", old_status, new_status),
    ("header", old_header_end, new_header_end),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-listen"
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
