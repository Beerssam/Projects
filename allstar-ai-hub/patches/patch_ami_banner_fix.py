#!/usr/bin/env python3
"""Fix for the AMI observer in /home/asl/ai_orchestrator.py (AllStar AI hub).

BUG: the observer reads the AMI greeting with _read_block(), which waits for a
blank line (CRLF CRLF). But the AMI greeting is a SINGLE line
("Asterisk Call Manager/x.y.z" + CRLF), with no blank line after it. So the
read waits forever and times out every 10 s, the observer never logs in, and
no RPT_RXKEYED / RPT_TXKEYED events are ever seen. The log shows this as
"[AMI] Observer error (timed out); retrying in 10s." repeating every ~20 s.
The main loop is unaffected (the observer is log-only and fail-safe).

FIX: read the greeting as a single line with a new _read_line() helper, and
keep using _read_block() for the login response and events (those ARE
blank-line terminated). This works whether or not the greeting is followed
by a blank line.

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

Run as root (or with sudo):  sudo python3 patch_ami_banner_fix.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Then watch the log:          tail -f /var/log/ai_orchestrator.log
Look for: "[AMI] Observer connected (log-only)." and "[AMI EVENT]" lines.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_ami_fix.py"


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

    def insert_after(marker, block, what):
        i = find(marker, what)
        lines[i + 1:i + 1] = block_lines(block)
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")
    # 1. Read the AMI greeting as a single line, not a blank-line-terminated block
    replace_token("_read_block(sock)  # banner", "_read_block(sock)  # banner", "_read_line(sock)  # banner (single line, not a block)", "read AMI greeting as a line")
    # 2. Add the _read_line helper right after _read_block
    insert_after('return block.decode(errors="replace")', r"""
    def _read_line(sock):
        while b"\r\n" not in buf[0]:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("AMI closed the connection")
            buf[0] += chunk
        line, buf[0] = buf[0].split(b"\r\n", 1)
        return line.decode(errors="replace")
""", "add _read_line helper")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Then watch: tail -f /var/log/ai_orchestrator.log")
    print("Look for: [AMI] Observer connected (log-only). and [AMI EVENT] lines.")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()
