# Leg gateway instances — clone-and-patch spec

The YSF / P25 / NXDN leg gateways are NOT authored from scratch. At
install time, `install-xmode.sh` clones the node's own working gateway
ini and rewrites only the lines below (python, section-scoped). This
keeps every other setting — host files, passwords, timings — identical
to the gateway that already works on the node, per Sam's principle
that the setup differs from stock only where intended.

Rules for the patcher:
- REQUIRED keys must exist exactly once in the named section; if not,
  the installer stops with a clear message and changes nothing.
- OPTIONAL keys are patched when present; when absent, the installer
  prints a warning and continues (they affect only remote-command
  control or network-side binds that may not exist in this build).
- `[Network] Startup` must exist after patching: the patcher sets it
  if present, adds it to [Network] if the section exists but the key
  does not. The bridge helper later rewrites Startup + restarts the
  leg stack to retune (the ini-as-source-of-truth pattern proven by
  the M17 bridge).

## YSFGateway: /opt/YSFGateway/YSFGateway.ini -> /opt/xmode/legs/ysf/YSFGateway.ini
- REQUIRED [General] RptPort: 4200 -> 4300        (faces leg MMDVM_Bridge)
- REQUIRED [Log] FilePath -> /var/log/mmdvm ; FileRoot -> YSFGateway-XYSF
- OPTIONAL [Remote Commands] Port: 6073 -> 6173
- OPTIONAL [Network] Port: 42001 -> 42021        (if this build binds it)
- [Network] Startup -> (blank default; helper sets the reflector)

## P25Gateway: /opt/P25Gateway/P25Gateway.ini -> /opt/xmode/legs/p25/P25Gateway.ini
- REQUIRED [General] RptPort: 32010 -> 33010
- REQUIRED [Log] FilePath -> /var/log/mmdvm ; FileRoot -> P25Gateway-XP25
- OPTIONAL [Remote Commands] Port: 6074 -> 6174
- OPTIONAL [Network] Port: 41000 -> 41010
- [Network] Startup -> (blank default; helper sets the reflector)

## NXDNGateway: /opt/NXDNGateway/NXDNGateway.ini -> /opt/xmode/legs/nxdn/NXDNGateway.ini
- REQUIRED [General] RptPort: 14021 -> 33021
- REQUIRED [Log] FilePath -> /var/log/mmdvm ; FileRoot -> NXDNGateway-XNXDN
- OPTIONAL [Remote Commands] Port: 6075 -> 6175
- OPTIONAL [Network] Port: 14050 -> 14051
- [Network] Startup -> (blank default; helper sets the talkgroup)

Log FilePath note: the main gateways log under /var/log/mmdvm already
(FileRoot distinguishes the files), so the legs share that directory
with their own FileRoots instead of inventing new log dirs.
