#!/usr/bin/env python3
"""Hub landing page: fix the Web Admin Portal link so it lands on THIS hub.

Root cause (Nov 24, from live /var/www/html/js/index.js): the Portal link is
built in JS as `https://<hostname>:9090` -- port 9090 is hardcoded. Locally
that is correct (https://192.168.1.200:9090/), but when the landing page is
opened remotely as 625731.nodes.allstarlink.org:8180, the link becomes
https://625731.nodes.allstarlink.org:9090 -- and through the AllStarLink
proxy, port 9090 reaches node 625730, while THIS hub's Cockpit is exposed on
9091 (confirmed: 625731.nodes.allstarlink.org:9091 loads Cockpit with
"Server: Allstar-Hub"). So the link sends Sam to the other node.

Fix (1 edit): make the Cockpit port depend on the hostname -- 9091 when the
page was opened on a *.nodes.allstarlink.org address, 9090 otherwise (local
IP / local hostname). The Allmon3 link is untouched.
- Target: /var/www/html/js/index.js (505 bytes, served by Apache).
- Backup: /home/asl/backups/20261124/index.js (created by this script).
- Writes via temp file + copy; aborts safely if the anchor is missing.
- No service restart needed (static file; browsers pick it up on reload,
  may need a hard refresh / cache clear).
"""
import os
import shutil
import sys

TARGET = "/var/www/html/js/index.js"
BACKUP_DIR = "/home/asl/backups/20261124"
BACKUP = os.path.join(BACKUP_DIR, "index.js")
TMP = "/tmp/index_portal_link.js"

if not os.path.isfile(TARGET):
    print("PATCH ABORTED: target %s not found" % TARGET)
    sys.exit(1)

os.makedirs(BACKUP_DIR, exist_ok=True)
if not os.path.isfile(BACKUP):
    shutil.copyfile(TARGET, BACKUP)
    print("backup saved: %s" % BACKUP)
else:
    print("backup already exists: %s (leaving it)" % BACKUP)

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

old = "    cockpitLink.href = `https://${thisHostname}:9090`;"
new = "    const cockpitPort = thisHostname.endsWith('.nodes.allstarlink.org') ? '9091' : '9090';\n    cockpitLink.href = `https://${thisHostname}:${cockpitPort}`;"
if src.count(old) != 1:
    print("PATCH ABORTED: cockpit href anchor: expected exactly 1 occurrence, found %d" % src.count(old))
    sys.exit(1)
src = src.replace(old, new, 1)
print("ok: cockpit port now 9091 on *.nodes.allstarlink.org, 9090 otherwise")

# Basic sanity: backticks and braces must stay balanced, new text present.
if src.count("`") % 2 != 0:
    print("PATCH ABORTED: unbalanced backticks after edit")
    sys.exit(1)
if src.count("{") != src.count("}"):
    print("PATCH ABORTED: unbalanced braces after edit")
    sys.exit(1)
if "cockpitPort" not in src or ":9090`;" in src:
    print("PATCH ABORTED: replacement text not found / old text still present")
    sys.exit(1)

with open(TMP, "w", encoding="utf-8") as f:
    f.write(src)

shutil.copyfile(TMP, TARGET)
print("PATCH OK: all edits applied.")
print("Test: reload the hub landing page (hard refresh if needed), click Web Admin Portal --")
print("  from 625731.nodes.allstarlink.org:8180 it should open https://625731.nodes.allstarlink.org:9091 (Server: Allstar-Hub),")
print("  from http://192.168.1.200/ it should open https://192.168.1.200:9090.")
print("Rollback: cp %s %s" % (BACKUP, TARGET))
