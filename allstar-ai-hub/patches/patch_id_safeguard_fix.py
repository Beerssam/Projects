#!/usr/bin/env python3
"""Fix the missed second copy of the 'aihub' check (AllStar AI hub).

WHAT IT FIXES (found by the audio test re-run, Nov 23 ~10:25):
  The Stage 1 Whisper gate was narrowed to only the full phrase
  "artificial intelligence hub", and the gate now passes a clip that
  says "AI hub". But a SECOND copy of the same check was left in
  process_audio() — the ID SAFEGUARD at line 345 — and it still drops
  any transcript containing the bare substring "aihub". The file-drop
  test passed the gate and was then dropped by this safeguard, so
  Gemini never saw it. This patch narrows that second check the same
  way: only the full phrase "artificialintelligencehub" counts as the
  hub's own voice. The beacon still says the full phrase, so it is
  still caught; a user saying "AI hub" is no longer dropped.

SAFETY:
- Refuses to run unless the verified backup exists at
  /home/asl/backups/20261122/ai_orchestrator.py
- The edit asserts its target line exists exactly once; if the check
  fails, NOTHING is written.
- Writes to a temp file, syntax-checks it with py_compile, and only
  then copies it into place (shutil.copyfile, so it works across
  filesystems).
- Rollback: cp /home/asl/backups/20261122/ai_orchestrator.py \
               /home/asl/ai_orchestrator.py
            sudo systemctl restart ai_orchestrator.service

Run as root (or with sudo):  sudo python3 patch_id_safeguard_fix.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Then watch the log:          tail -f /var/log/ai_orchestrator.log
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_id_safeguard_fix.py"


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

    def replace_token(marker, old, new, what):
        i = find(marker, what)
        if old not in lines[i]:
            fail("line for %s does not contain %r: %r" % (what, old, lines[i]))
        lines[i] = lines[i].replace(old, new, 1)
        print("  ok: " + what)

    def insert_before(marker, block, what):
        i = find(marker, what)
        lines[i:i] = block_lines(block)
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")
    # ID SAFEGUARD: only the full phrase counts as our own voice
    replace_token('"artificialintelligencehub" in match_transcript or "aihub" in match_transcript', '"artificialintelligencehub" in match_transcript or "aihub" in match_transcript', '"artificialintelligencehub" in match_transcript', "ID safeguard: full phrase only, not bare 'aihub'")
    insert_before('if "artificialintelligencehub" in match_transcript:', r"""
    # Full phrase only: bare "ai hub" appears in normal speech (e.g. "testing the AI hub").
""", "ID safeguard: explain full-phrase check")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Then watch: tail -f /var/log/ai_orchestrator.log")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()
