#!/usr/bin/env python3
"""ID beacon robustness fix for the AI hub orchestrator.
Two changes:
(a) Hold the FCC ID when the channel is busy. In check_and_run_fcc_id(),
    skip the ID if someone is currently keyed (AMI tx_keyed) or if a monitor
    file appeared in the last 20 s (a user just transmitted). The ID retries
    on the next loop iteration; if the channel stays busy past the minute it
    waits for the next 10-minute mark. This stops the ID from firing on top
    of a user's transmission.
(b) Time-bound the bypass flag. A DASHBOARD BYPASS drop now only applies to
    a monitor file that started within 12 s of the flag file being set (our
    own playback). A file created well after the flag was set is a real user
    transmission that arrived after the ID, so it is no longer swallowed by
    the flag and falls through to the Whisper gate.
This patch edits by line content (robust to indentation). It aborts safely
if any anchor is missing.
Target: /home/asl/ai_orchestrator.py.
Backup required: /home/asl/backups/20261122/ai_orchestrator.py.
"""
import os
import sys
import shutil
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_idfix_patched.py"

if not os.path.exists(BACKUP):
    print("PATCH ABORTED: verified backup %s not found" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    lines = f.readlines()

def find_line(needle, start=0):
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i
    return -1

def indent_of(i):
    s = lines[i]
    return s[:len(s) - len(s.lstrip())]

# --- (a) busy check in check_and_run_fcc_id ---
idx_def = find_line("def check_and_run_fcc_id():")
if idx_def < 0:
    print("PATCH ABORTED: check_and_run_fcc_id def not found")
    sys.exit(1)
idx_ts = find_line('ts_log("FCC CLOCK BEACON"', idx_def)
if idx_ts < 0:
    print("PATCH ABORTED: FCC CLOCK BEACON log line not found")
    sys.exit(1)
ind = indent_of(idx_ts)
busy_lines = [
    ind + "# --- ROBUSTNESS: hold the ID if someone is talking or just talked ---\n",
    ind + "if global_state.get(\"tx_keyed\"):\n",
    ind + "    return\n",
    ind + "# If a monitor file appeared in the last 20s, a user just transmitted; hold the ID.\n",
    ind + "try:\n",
    ind + "    _now = time.time()\n",
    ind + "    for _p in glob.glob(os.path.join(STREAM_DIR, \"*.wav\")):\n",
    ind + "        if os.path.getmtime(_p) > (_now - 20.0):\n",
    ind + "            return\n",
    ind + "except Exception:\n",
    ind + "    pass\n",
]
lines[idx_ts:idx_ts] = busy_lines
print("ok: (a) hold ID when channel busy / user just transmitted")

# --- (b) time-bound the bypass flag in monitor_directory ---
idx_flag = find_line('is_dashboard_id = False')
if idx_flag < 0:
    print("PATCH ABORTED: is_dashboard_id = False not found")
    sys.exit(1)
idx_if = find_line('if os.path.exists("/tmp/ai_dash_cooldown")', idx_flag)
if idx_if < 0:
    print("PATCH ABORTED: flag-exists check not found")
    sys.exit(1)
idx_set = find_line('is_dashboard_id = True', idx_if)
if idx_set < 0:
    print("PATCH ABORTED: is_dashboard_id = True not found")
    sys.exit(1)
# The flag block is lines idx_flag .. idx_set (inclusive). Replace it.
ind2 = indent_of(idx_flag)
new_block = [
    ind2 + "# A bypass flag only drops a file that started within 12s of the flag\n",
    ind2 + "# being set (our own playback). A file created well after the flag is\n",
    ind2 + "# a real user transmission, so it is NOT dropped here.\n",
    ind2 + "is_dashboard_id = False\n",
    ind2 + "for _flag in [\"/tmp/ai_dash_cooldown\", \"/var/run/ai_dash_active\"]:\n",
    ind2 + "    if os.path.exists(_flag):\n",
    ind2 + "        try:\n",
    ind2 + "            _flag_time = os.path.getmtime(_flag)\n",
    ind2 + "        except Exception:\n",
    ind2 + "            _flag_time = 0.0\n",
    ind2 + "        if file_creation_time < (_flag_time + 12.0):\n",
    ind2 + "            is_dashboard_id = True\n",
    ind2 + "            break\n",
]
lines[idx_flag:idx_set + 1] = new_block
print("ok: (b) bypass flag only drops files that started within 12s of the flag")

with open(TMP, "w", encoding="utf-8") as f:
    f.writelines(lines)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
