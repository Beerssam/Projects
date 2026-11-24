#!/usr/bin/env python3
"""Hub: answer health/status questions with live Pi data.

When Sam asks how the hub is doing, for a status check, or about the
Pi/hub health ("how are you", "status", "what's the Pi's health",
"what's your health", "temperature", "uptime", ...), the orchestrator
gathers the Pi's live health and hands it to Gemini in the prompt, so
she answers with real numbers instead of guessing.

Same conditional pattern as ADS-B (Nov 23): the health data is only
included when the Whisper transcript asks about health/status, so
normal calls stay lean. Fail OPEN on an empty transcript (Whisper
failed) so a health question is never missed.

Health data (all read live on the Pi, stdlib only):
- Pi uptime (from /proc/uptime)
- 1-min CPU load (os.getloadavg)
- CPU temp (thermal_zone0, if present)
- Disk free (os.statvfs)
- Memory available (/proc/meminfo)
- AI service running (it is, since it is answering)

Requires backup /home/asl/backups/20261122/ai_orchestrator.py.
Writes via temp file + py_compile + shutil.copyfile; aborts safely if
any anchor is not found exactly once. Does NOT touch the ADS-B
keywords, so it applies cleanly whether or not patch_hub_faster_sky
has been run.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_health.py"


def fail(msg):
    print("PATCH ABORTED: " + msg)
    sys.exit(1)


def main():
    if not os.path.exists(BACKUP):
        fail("verified backup not found at " + BACKUP + "; refusing to change anything.")
    with open(TARGET) as f:
        lines = f.readlines()

    def find(marker, what):
        hits = [i for i, ln in enumerate(lines) if marker in ln]
        if len(hits) != 1:
            fail("expected exactly 1 line containing %r for %s, found %d" % (marker, what, len(hits)))
        return hits[0]

    def block_lines(block):
        return [ln + "\n" for ln in block.strip("\n").split("\n")]

    def insert_before(marker, block, what):
        i = find(marker, what)
        lines[i:i] = block_lines(block)
        print("  ok: " + what)

    def insert_after(marker, block, what):
        i = find(marker, what)
        lines[i + 1:i + 1] = block_lines(block)
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")

    # (1) get_hub_health() before get_nearby_flights().
    insert_before(
        "def get_nearby_flights():",
        '''
def get_hub_health():
    """Live Pi/hub health as a short prompt block (stdlib only)."""
    try:
        with open("/proc/uptime") as _uf:
            _up_s = float(_uf.read().split()[0])
    except Exception:
        _up_s = 0.0
    _d = int(_up_s // 86400)
    _h = int((_up_s % 86400) // 3600)
    _m = int((_up_s % 3600) // 60)
    _up_str = (f"{_d}d {_h}h" if _d else (f"{_h}h {_m}m" if _h else f"{_m}m"))
    try:
        _load1 = os.getloadavg()[0]
    except Exception:
        _load1 = None
    _temp_c = None
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as _tf:
            _temp_c = int(_tf.read().strip()) / 1000.0
    except Exception:
        pass
    try:
        _st = os.statvfs("/")
        _free_gb = _st.f_bavail * _st.f_frsize / (1024 ** 3)
    except Exception:
        _free_gb = None
    _mem_gb = None
    try:
        with open("/proc/meminfo") as _mf:
            for _line in _mf:
                if _line.startswith("MemAvailable:"):
                    _mem_gb = int(_line.split()[1]) / (1024 ** 2)
                    break
    except Exception:
        pass
    _parts = [f"Pi uptime {_up_str}"]
    if _load1 is not None:
        _parts.append(f"1-min CPU load {_load1:.2f}")
    if _temp_c is not None:
        _parts.append(f"CPU temp {_temp_c:.1f} C")
    if _free_gb is not None:
        _parts.append(f"disk free {_free_gb:.0f} GB")
    if _mem_gb is not None:
        _parts.append(f"memory available {_mem_gb:.1f} GiB")
    _parts.append("AI service running")
    return (
        "HUB HEALTH (live, just now -- if asked how the hub/Pi is doing, "
        "for a status check, or about its health, answer using this data): "
        + "; ".join(_parts) + ".\\n\\n"
    )

''',
        "get_hub_health() function")

    # (2) Conditional health block, right after the ADS-B if/else.
    # Anchor on the else-branch line `adsb_block = ""` (unique). The
    # inserted block runs at process_audio body level (4 spaces), after
    # the ADS-B block, and reuses _gate_low defined just above.
    insert_after(
        '        adsb_block = ""',
        '''
    # Hub health only when the caller asks about the hub/Pi status.
    # Same pattern as ADS-B: check the Whisper transcript for health
    # words. Fail OPEN on an empty transcript so a health question is
    # never missed because of a bad transcript.
    _health_words = ("how are you", "how are you doing", "how's it going", "hows it going", "status", "status check", "health", "temperature", "temp", "uptime", "cpu", "load", "disk", "memory", "ram", "are you okay", "are you ok", "everything good", "everything ok", "everything okay", "how long")
    _want_health = (not _gate_low) or any(w in _gate_low for w in _health_words)
    if _want_health:
        health_block = get_hub_health()
    else:
        health_block = ""
''',
        "conditional health block")

    # (3) Include health_block in the prompt alongside adsb_block.
    # The prompt has one line `f"{adsb_block}"`; extend it.
    i = find('f"{adsb_block}"', "prompt ADS-B block line")
    if 'health_block' in lines[i]:
        fail("health_block already in prompt line; refusing to edit twice.")
    lines[i] = lines[i].replace('f"{adsb_block}"', 'f"{adsb_block}{health_block}"', 1)
    print("  ok: prompt includes health_block")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Test: ask 'how are you doing' / 'status check' / 'what is the Pi health' -- she should answer with real uptime, load, temp, disk, memory.")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()
