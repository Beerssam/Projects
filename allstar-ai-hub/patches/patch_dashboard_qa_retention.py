#!/usr/bin/env python3
"""Dashboard: keep more Q&As in the Recent Questions & Answers panel.

Root cause (Nov 23, from the live ai_dashboard.py): /api/recent reads only
the last 300 lines of /var/log/ai_orchestrator.log and returns only the last
5 Q&A pairs (items[-5:]). The log is very chatty (Whisper gate, API, TTS,
playback, and AMI event lines per question), so 300 lines only covers the
last couple of questions before older ones scroll out of the window.

Fix (2 edits):
- recent_api tail 300 -> 1500 lines (covers ~50-75 questions instead of ~2).
- return items[-5:] -> items[-15:] (show up to 15 instead of 5).
- Only the /api/recent endpoint changes; ai_status and pool still read 300.
- Requires backup /home/asl/backups/20261123/ai_dashboard.py.
- Writes via temp file + py_compile + shutil.copyfile; aborts safely if an
  anchor is missing.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_dashboard.py"
BACKUP = "/home/asl/backups/20261123/ai_dashboard.py"
TMP = "/tmp/ai_dashboard_qa_retention.py"

if not os.path.isfile(BACKUP):
    print("PATCH ABORTED: backup %s not found; refusing to edit live file" % BACKUP)
    sys.exit(1)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

# (1) recent_api: read 1500 log lines instead of 300.
# Two-line anchor is unique to recent_api (pool_api's loop checks GEMINI RESPONSE).
old1 = '    for line in _tail_log(300):\n        if "[RADIO INTERPRETATION]" in line and "Heard:" in line:'
new1 = '    for line in _tail_log(1500):\n        if "[RADIO INTERPRETATION]" in line and "Heard:" in line:'
if src.count(old1) != 1:
    print("PATCH ABORTED: recent_api tail anchor: expected exactly 1 occurrence, found %d" % src.count(old1))
    sys.exit(1)
src = src.replace(old1, new1, 1)
print("ok: recent_api log tail 300 -> 1500 lines")

# (2) Show up to 15 Q&A pairs instead of 5.
old2 = '    return jsonify({"items": items[-5:]})'
new2 = '    return jsonify({"items": items[-15:]})'
if src.count(old2) != 1:
    print("PATCH ABORTED: items[-5:] anchor: expected exactly 1 occurrence, found %d" % src.count(old2))
    sys.exit(1)
src = src.replace(old2, new2, 1)
print("ok: Q&A cap 5 -> 15 items")

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

try:
    py_compile.compile(TMP, doraise=True)
except py_compile.PyCompileError as e:
    print("PATCH ABORTED: syntax check failed: %s" % e)
    sys.exit(1)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied and syntax-checked.")
print("Restart the dashboard: sudo systemctl restart ai_dashboard.service")
print("Rollback: cp /home/asl/backups/20261123/ai_dashboard.py /home/asl/ai_dashboard.py && sudo systemctl restart ai_dashboard.service")
