#!/usr/bin/env python3
"""Two small fixes for /home/asl/ai_orchestrator.py (AllStar AI hub, Stage 1).

FIX 1 — Whisper gate false positive (found by the audio test, Nov 23 ~09:23):
  The gate dropped a test clip that said "testing the AI hub" because its
  own-voice check looked for the bare substring "aihub" anywhere in the
  transcript. Any normal transmission that mentions "AI hub" would be
  dropped the same way. Fix: only match the FULL phrase
  "artificialintelligencehub" (the words in the hub's own beacon/ID).
  The bare "AI hub" in ordinary speech no longer triggers the drop.

FIX 2 — AMI observer drops its connection while idle (found Nov 23 ~09:23):
  After logging in, the observer's socket still has the 10 s connect
  timeout, so when the node is idle and no event arrives within 10 s,
  the read times out, the observer logs an error and reconnects, over
  and over (~20 s cycle). It does connect (the greeting fix worked), but
  it never stays connected long enough to be useful. Fix: set the socket
  to blocking (no timeout) after a successful login, so it waits
  patiently for the next event. A real disconnect still raises and
  reconnects via the existing retry loop.

SAFETY:
- Refuses to run unless the verified backup exists at
  /home/asl/backups/20261122/ai_orchestrator.py
- Every edit asserts its target line exists exactly once; if any check
  fails, NOTHING is written.
- Writes to a temp file, syntax-checks it with py_compile, and only then
  copies it into place (shutil.copyfile, so it works across filesystems).
- Rollback: cp /home/asl/backups/20261122/ai_orchestrator.py \
               /home/asl/ai_orchestrator.py
            sudo systemctl restart ai_orchestrator.service

Run as root (or with sudo):  sudo python3 patch_stage1_gate_ami_fix.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Then watch the log:          tail -f /var/log/ai_orchestrator.log
Look for: "[AMI] Observer connected (log-only)." staying connected (no more
"Observer error (timed out)" lines), and "[AMI EVENT]" lines when the node
keys/unkeys. The Whisper gate fix is proven by the next audio test.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_gate_ami_fix.py"


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
    # FIX 1 — Whisper gate: only the full phrase counts as our own voice
    replace_token('"artificialintelligencehub" in norm or "aihub" in norm', '"artificialintelligencehub" in norm or "aihub" in norm', '"artificialintelligencehub" in norm', "gate: full phrase only, not bare 'aihub'")
    insert_before('if "artificialintelligencehub" in norm:', r"""
    # Full phrase only: bare "ai hub" appears in normal speech (e.g. "testing the AI hub").
""", "gate: explain full-phrase check")
    # FIX 2 — AMI observer: wait patiently for events after login (no timeout while idle)
    insert_before('sock.sendall(b"Action: Events', r"""
            sock.settimeout(None)  # wait patiently for events; no timeout while idle
""", "AMI: blocking socket after login")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Then watch: tail -f /var/log/ai_orchestrator.log")
    print("Look for: [AMI] Observer connected (log-only). staying connected, and [AMI EVENT] lines.")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()
