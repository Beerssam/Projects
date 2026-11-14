# Leg gateway instances — clone-and-patch spec

The YSF / P25 / NXDN leg gateways are NOT authored from scratch. At
install time, `install-xmode.sh` clones the node's own working gateway
ini and rewrites only the lines below (python, section-scoped). This
keeps every other setting — host files, parrot addresses, timings —
identical to the gateway that already works on the node, per Sam's
principle that the setup differs from stock only where intended.

**Expected values below are from the node's LIVE gateway inis
(Nov 13 2026)**, not stock DVSwitch values — the live files differ
from stock in exactly the ports that matter here (the first install
attempts proved it). The patcher specs live in each leg's
`gateway.patch`.

Pairing rule (from the node's working YSF chain, the one mode whose
gateway pairing is exact): a gateway's `[General] RptPort` equals
its MMDVM_Bridge network LocalPort, and its `[General] LocalPort`
equals the bridge's GatewayPort. The legs are wired exactly; note
the stock main chain pairs P25/NXDN off by one (gateway RptPort
32010/14021 vs bridge LocalPort 32011/14022), a possible reason
main-chain P25/NXDN gateway traffic has never flowed.

Rules for the patcher:
- REQUIRED keys must exist exactly once in the named section; if
  not, the installer stops with a clear message and changes
  nothing.
- OPTIONAL keys are patched when present; when absent, the
  installer prints a warning and continues.
- `[Network] Startup` must exist after patching (ENSURE): set if
  present, appended to [Network] if not (a commented-out Startup
  line does not count). The bridge helper later rewrites Startup +
  restarts the leg gateway to retune (the ini-as-source-of-truth
  pattern proven by the M17 bridge).

## YSFGateway -> /opt/xmode/legs/ysf/YSFGateway.ini
- REQUIRED [General] RptPort: 3200 -> 3300 ; LocalPort: 4200 -> 4300
- REQUIRED [Log] FilePath -> /var/log/mmdvm ; FileRoot -> YSFGateway-XYSF
- REQUIRED [YSF Network] Port: 42000 -> 42400 ; [FCS Network] Port: 42001 -> 42401
- OPTIONAL [Remote Commands] Port: 6073 -> 6173
- ENSURE [Network] Startup
- Untouched on purpose: ParrotPort 42012 (a destination, not a bind —
  the leg shares the node's YSF parrot), Id, host files.

## P25Gateway -> /opt/xmode/legs/p25/P25Gateway.ini
- REQUIRED [General] RptPort: 32010 -> 33011 ; LocalPort: 42020 -> 33010
- REQUIRED [Log] FilePath -> /var/log/mmdvm ; FileRoot -> P25Gateway-XP25
- REQUIRED [Network] Port: 42010 -> 42410
- OPTIONAL [Remote Commands] Port: 6074 -> 6174
- ENSURE [Network] Startup
- Untouched: ParrotPort 42011 / P252DMRPort 42012 (destinations).

## NXDNGateway -> /opt/xmode/legs/nxdn/NXDNGateway.ini
- REQUIRED [General] RptPort: 14021 -> 33022 ; LocalPort: 14020 -> 33021
- REQUIRED [Log] FilePath -> /var/log/mmdvm ; FileRoot -> NXDNGateway-XNXDN
- REQUIRED [Network] Port: 14050 -> 14051
- OPTIONAL [Remote Commands] Port: 6075 -> 6175
- ENSURE [Network] Startup
- Untouched: ParrotPort 42021 / NXDN2DMRPort 42022 (destinations),
  and the commented Kenwood/Icom RptPort lines (comments, not keys).

Log FilePath note: the main gateways log under /var/log/mmdvm
already (FileRoot distinguishes the files), so the legs share that
directory with their own FileRoots.
