#!/usr/bin/env python3
"""Solar panel readability fix for the AI hub dashboard (ai_dashboard.py).

Sam (Nov 24 12:08 CST) said the solar panel works but is hard to read, and the
VHF line shows "&middot;" as literal text. Two fixes:
  1. VHF joiner: pollSolar() sets the VHF line with textContent, which does NOT
     parse HTML entities, so '&middot;' showed literally. Use a real middle
     dot character instead.
  2. Readability: bump the four solar stat-lines to 1rem with line-height 1.6
     so the values are larger and less cramped on a phone.

Backups: the script refuses to run unless it can write a backup copy first.
Rollback: cp <backup> /home/asl/ai_dashboard.py && sudo systemctl restart ai_dashboard
Run on the hub as: sudo python3 patch_dashboard_solar_readability.py
"""
import os
import shutil
import sys

TARGET = '/home/asl/ai_dashboard.py'
BACKUP_DIR = '/home/asl/backups/20261124'
BACKUP = os.path.join(BACKUP_DIR, 'ai_dashboard.py.solar_readability')

EDITS = [
    # 1. Larger, roomier solar stat-lines (was small dense monospace).
    (
        "    <div class=\"stat-line\" id=\"solar-top\">Loading solar data...</div>\n    <div class=\"stat-line\" id=\"solar-mid\"></div>\n    <div class=\"stat-line\" id=\"solar-hf\"></div>\n    <div class=\"stat-line\" id=\"solar-vhf\"></div>",
        "    <div class=\"stat-line\" id=\"solar-top\" style=\"font-size:1rem;line-height:1.6;\">Loading solar data...</div>\n    <div class=\"stat-line\" id=\"solar-mid\" style=\"font-size:1rem;line-height:1.6;\"></div>\n    <div class=\"stat-line\" id=\"solar-hf\" style=\"font-size:1rem;line-height:1.6;\"></div>\n    <div class=\"stat-line\" id=\"solar-vhf\" style=\"font-size:1rem;line-height:1.6;\"></div>",
    ),
    # 2. VHF joiner: real middle dot, not the literal "&middot;" string.
    # textContent does not parse HTML entities, so the entity showed as text.
    (
        "vhf.textContent = 'VHF: ' + d.vhf.map(function(p){ return p.label + ' ' + p.value; }).join(' &middot; ');",
        "vhf.textContent = 'VHF: ' + d.vhf.map(function(p){ return p.label + ' ' + p.value; }).join(' \u00b7 ');",
    ),
]

def main():
    if not os.path.exists(TARGET):
        print('PATCH ABORTED: target %s not found' % TARGET)
        return 1
    with open(TARGET, 'r') as f:
        src = f.read()
    for i, (old, new) in enumerate(EDITS, 1):
        if old not in src:
            print('PATCH ABORTED: edit %d anchor not found' % i)
            return 1
        if src.count(old) != 1:
            print('PATCH ABORTED: edit %d anchor not unique (%d matches)' % (i, src.count(old)))
            return 1
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(TARGET, BACKUP)
    print('backup saved: %s' % BACKUP)
    for i, (old, new) in enumerate(EDITS, 1):
        src = src.replace(old, new, 1)
        print('edit %d ok' % i)
    with open(TARGET, 'w') as f:
        f.write(src)
    print('PATCH OK (%d edits)' % len(EDITS))
    return 0

if __name__ == '__main__':
    sys.exit(main())
