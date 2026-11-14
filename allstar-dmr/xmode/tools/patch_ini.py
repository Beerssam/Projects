#!/usr/bin/env python3
"""patch_ini.py -- section-scoped ini patcher for the xmode installer.

Usage: patch_ini.py <src.ini> <dst.ini> <spec.txt>
(src == dst for in-place edits.)

Spec lines (pipe-delimited, '#' comments):
  R|Section|Key|Expected|New
      REQUIRED. The key must exist exactly once in the section, and its
      current value must be Expected (or already New -> no-op).
      Expected may be '*' to accept any current value. The line is
      rewritten to New, preserving any trailing ';' comment.
  O|Section|Key|Expected|New
      OPTIONAL. If the key exists once and equals Expected, rewrite to
      New. If absent, warn and continue. If present with another
      value, warn and leave it (never silently force an optional).
  E|Section|Key|New
      ENSURE. Set the key if present; if absent, append it at the end
      of the section. The section must exist.

Values are compared as bare tokens (quotes stripped). Any REQUIRED
miss prints 'PATCH-ERROR ...' and exits 1 with NOTHING written.
On success prints one 'patched <Section> <Key>: <old> -> <new>' or
'already <Section> <Key>=<new>' line per spec entry, plus warnings as
'PATCH-WARN ...'. Secrets policy: callers must not put secret values
in spec files; password fills are done by install-xmode.sh directly
in memory and never pass through specs or logs.
"""

import sys


def parse_ini(text):
    """Return (lines, sections) where sections maps name -> list of
    (index, key, value) for key lines, preserving the raw text."""
    lines = text.splitlines()
    sections = {}
    current = None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1].strip()
            sections.setdefault(current, [])
            continue
        if current is not None and "=" in raw and not s.startswith((";", "#")):
            key = raw.split("=", 1)[0].strip()
            val = raw.split("=", 1)[1].strip()
            if ";" in val:
                val = val.split(";", 1)[0].strip()
            sections[current].append((i, key, val.strip('"')))
    return lines, sections


def find(sections, section, key):
    return [(i, v) for (i, k, v) in sections.get(section, []) if k == key]


def main(argv):
    src, dst, spec_path = argv[1], argv[2], argv[3]
    with open(src) as f:
        text = f.read()
    with open(spec_path) as f:
        specs = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

    lines, sections = parse_ini(text)
    edits = {}   # line index -> new line text
    appends = []  # (section, text) to append at section end
    errors, warnings, report = [], [], []

    for spec in specs:
        parts = spec.split("|")
        mode = parts[0]
        if mode in ("R", "O"):
            _, section, key, expected, new = parts
        elif mode == "E":
            _, section, key, new = parts
            expected = None
        else:
            errors.append(f"PATCH-ERROR bad spec line: {spec}")
            continue

        if section not in sections:
            if mode == "O":
                warnings.append(f"PATCH-WARN [{section}] absent; skipped {key}")
                continue
            errors.append(f"PATCH-ERROR [{section}] section not found (for {key})")
            continue

        hits = find(sections, section, key)
        if mode == "E":
            if len(hits) == 1:
                i, cur = hits[0]
                if cur == new:
                    report.append(f"already [{section}] {key}={new}")
                else:
                    edits[i] = ("SET", i, key, new)
                    report.append(f"patched [{section}] {key}: {cur} -> {new}")
            elif len(hits) == 0:
                appends.append((section, f"{key}={new}"))
                report.append(f"added [{section}] {key}={new}")
            else:
                errors.append(f"PATCH-ERROR [{section}] {key} appears {len(hits)} times")
            continue

        # R / O
        if len(hits) == 0:
            if mode == "R":
                errors.append(f"PATCH-ERROR [{section}] {key} not found")
            else:
                warnings.append(f"PATCH-WARN [{section}] {key} absent; skipped")
            continue
        if len(hits) > 1:
            errors.append(f"PATCH-ERROR [{section}] {key} appears {len(hits)} times")
            continue
        i, cur = hits[0]
        if cur == new:
            report.append(f"already [{section}] {key}={new}")
        elif expected == "*" or cur == expected:
            edits[i] = ("SET", i, key, new)
            report.append(f"patched [{section}] {key}: {cur} -> {new}")
        else:
            msg = f"[{section}] {key} is '{cur}', expected '{expected}'"
            if mode == "R":
                errors.append(f"PATCH-ERROR {msg}")
            else:
                warnings.append(f"PATCH-WARN {msg}; left unchanged")

    if errors:
        for e in errors:
            print(e)
        return 1

    # Apply edits: rewrite just the value, keep the key's original
    # formatting up to '=' and any trailing comment.
    for item in list(edits.values()):
        _, i, key, new = item
        raw = lines[i]
        eq = raw.index("=")
        head = raw[: eq + 1]
        sep = " " if raw[eq + 1: eq + 2] in (" ", "\t") else ""
        comment = ""
        if ";" in raw:
            comment = " " + raw[raw.index(";"):]
        lines[i] = f"{head}{sep}{new}{comment}"

    # Appends: insert before the next section header after the target
    # section, or at EOF.
    if appends:
        out = []
        current = None
        pending = dict()
        for section, txt in appends:
            pending.setdefault(section, []).append(txt)
        for raw in lines:
            s = raw.strip()
            if s.startswith("[") and s.endswith("]"):
                if current in pending:
                    out.extend(pending.pop(current))
                current = s[1:-1].strip()
            out.append(raw)
        if current in pending:
            out.extend(pending.pop(current))
        lines = out

    with open(dst, "w") as f:
        f.write("\n".join(lines) + "\n")
    for w in warnings:
        print(w)
    for r in report:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
