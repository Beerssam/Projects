#!/usr/bin/env bash
# install-xmode.sh -- installs the DVSwitch-native cross-mode bridge
# (xmode/DESIGN.md, design v2) on Sam's ASL3 node.
#
# What it changes (and nothing else):
#   NEW  /opt/xmode/                 leg configs, usrp-agc, helper
#   NEW  /etc/USRP2M17-xmode.ini    M17 leg (own log dir)
#   NEW  systemd units for the leg stacks + usrp-agc@ template
#        (installed, NOT enabled -- leg stacks start on demand when
#        a bridge is started from the dashboard; only usrp-agc@main
#        is enabled + started, for the main chain)
#   EDIT /opt/Analog_Bridge/Analog_Bridge.ini  ([USRP] rx
#        34001 -> 32021, tx 32001 -> 34021 for the main AGC shim;
#        backup first; the ONLY edit to an existing config)
#   NO rpt.conf changes. NO Asterisk changes. The bridge is
#   digital-to-digital inside DVSwitch (Sam's direction, Nov 2026).
#
# Norms followed: preflight verifies the node's current setup and
# stops with a clear message on any mismatch; every existing file is
# backed up (timestamped) before it is touched; the leg gateway
# configs are CLONED from the node's own working gateway inis (ports
# + log names patched only); the leg DMRGateway's network passwords
# are recovered in-memory from the main DMRGateway.ini (the KS-DMR
# one is the published network passphrase) and are never printed,
# logged or committed; ends with a liveness report and generates a
# ROLLBACK.sh for this install.
#
# Env overrides (testing): XROOT, SYSTEMCTL, SKIP_PORT_CHECK

set -euo pipefail
[[ $EUID == 0 ]] || { echo "STOP: run as root (sudo bash install-xmode.sh)"; exit 1; }

XROOT="${XROOT:-}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TS=$(date +%Y%m%d-%H%M%S)

p() { echo "$XROOT$1"; }
say() { echo "== $*"; }
die() { echo "STOP: $*"; echo "Nothing was changed beyond what is listed above."; exit 1; }

MAIN_AB_INI=$(p /opt/Analog_Bridge/Analog_Bridge.ini)
MAIN_GW_INI=$(p /opt/DMRGateway/DMRGateway.ini)
RPT_MARKER=$(p /opt/xmode/.installed)

say "Preflight: binaries and existing configs"
for f in /opt/Analog_Bridge/Analog_Bridge /opt/MMDVM_Bridge/MMDVM_Bridge \
         /opt/YSFGateway/YSFGateway /opt/P25Gateway/P25Gateway \
         /opt/NXDNGateway/NXDNGateway /usr/local/bin/DMRGateway \
         /usr/local/bin/USRP2M17 \
         /opt/YSFGateway/YSFGateway.ini \
         /opt/P25Gateway/P25Gateway.ini \
         /opt/NXDNGateway/NXDNGateway.ini; do
  [[ -e "$(p "$f")" ]] || die "expected file missing: $f"
done
[[ -e "$MAIN_AB_INI" ]] || die "expected file missing: $MAIN_AB_INI"
[[ -e "$MAIN_GW_INI" ]] || die "expected file missing: $MAIN_GW_INI"
command -v python3 >/dev/null || die "python3 not found"

say "Preflight: main Analog_Bridge [USRP] ports (expect rx 34001 / tx 32001, or rx 32021 / tx 34021 if rerun)"
# NOTE: the live ini carries a bare "include = dvsm.macro" line before
# its first section header (dvs-generated file) -- configparser dies on
# that, so read the two ports with a section-scoped awk instead.
ab_ini_get() {
  awk -v key="$1" '
    /^\[/ { in_sec = ($0 == "[USRP]") }
    in_sec && $0 ~ "^" key "[ \t]*=" {
      v = $0; sub(/^[^=]*=[ \t]*/, "", v); sub(/[ \t;].*$/, "", v); print v; exit
    }' "$MAIN_AB_INI" 2>/dev/null
}
AB_RX="$(ab_ini_get rxPort) $(ab_ini_get txPort)"
case "$AB_RX" in
  "34001 32001") REWIRE=1 ;;
  "32021 34021") REWIRE=0; say "main AB already rewired for the shim (rx 32021 / tx 34021)" ;;
  *) die "main Analog_Bridge [USRP] ports are 'rx/tx $AB_RX' -- not the expected 34001/32001. Nothing changed." ;;
esac

if [[ ! -f "$RPT_MARKER" && "${SKIP_PORT_CHECK:-}" != 1 ]]; then
  say "Preflight: planned UDP binds must be free (first install)"
  BUSY=$(ss -ulnp 2>/dev/null | grep -E ':(32021|34021|34401|34402|34201|34211|34221|34231|34240|32013|31200|31203|35200|35203|32250|32253|33200|33203|62131|62132|3300|4300|33010|33011|33021|33022|6173|6174|6175|42400|42401|42410|14051)([[:space:]]|$)' || true)
  [[ -z "$BUSY" ]] || die "a planned port is already in use:
$BUSY"
fi

say "Change list"
echo "  * NEW /opt/xmode (leg configs, usrp-agc, xmode-switch helper)"
echo "  * NEW /etc/USRP2M17-xmode.ini + /var/log/usrp2m17-xmode/"
echo "  * NEW systemd units (leg stacks + usrp-agc@), NOT enabled;"
echo "    only usrp-agc@main is enabled + started"
echo "  * clone+patch the node's YSF/P25/NXDN gateway inis into the legs"
echo "  * leg DMRGateway passwords filled from the main gateway ini"
echo "    (in memory only -- never printed)"
[[ $REWIRE == 1 ]] && echo "  * back up + rewire $MAIN_AB_INI [USRP] rx 34001->32021, tx 32001->34021 (main AGC shim)"
echo "  * NO rpt.conf / Asterisk changes; 1998/1999/625730 untouched"

say "Backups"
BACKUP_XMODE=""
if [[ -d "$(p /opt/xmode)" ]]; then
  BACKUP_XMODE="$(p /opt/xmode).bak.$TS"
  cp -a "$(p /opt/xmode)" "$BACKUP_XMODE"
  echo "  backed up existing /opt/xmode -> $BACKUP_XMODE"
fi
BACKUP_AB=""
if [[ $REWIRE == 1 ]]; then
  BACKUP_AB="$MAIN_AB_INI.bak.xmode-$TS"
  cp -a "$MAIN_AB_INI" "$BACKUP_AB"
  echo "  backed up main Analog_Bridge.ini -> $BACKUP_AB"
fi

say "Installing /opt/xmode"
mkdir -p "$(p /opt/xmode/legs)" "$(p /opt/xmode/usrp-agc)" "$(p /opt/xmode/tools)" "$(p /var/log/usrp2m17-xmode)"
cp -a "$SRC_DIR/usrp-agc/usrp_agc.py" "$SRC_DIR/usrp-agc/usrp-agc-main.ini" "$(p /opt/xmode/usrp-agc/)"
cp -a "$SRC_DIR/DESIGN.md" "$(p /opt/xmode/)" 2>/dev/null || true
cp -a "$SRC_DIR/tools/patch_ini.py" "$(p /opt/xmode/tools/)"
install -m 0755 "$SRC_DIR/xmode-switch.sh" "$(p /opt/xmode/xmode-switch.sh)"
for leg in dmr ysf p25 nxdn; do
  mkdir -p "$(p /opt/xmode/legs/$leg)"
  cp -a "$SRC_DIR/legs/$leg/Analog_Bridge.ini" "$SRC_DIR/legs/$leg/MMDVM_Bridge.ini" "$SRC_DIR/legs/$leg/DVSwitch.ini" "$(p /opt/xmode/legs/$leg/)"
done
cp -a "$SRC_DIR/legs/dmr/DMRGateway.ini" "$(p /opt/xmode/legs/dmr/DMRGateway.ini)"
install -m 0644 "$SRC_DIR/legs/m17/USRP2M17-xmode.ini" "$(p /etc/USRP2M17-xmode.ini)"

say "Cloning the node's gateway inis into the legs (patch ports/logs only)"
python3 "$(p /opt/xmode/tools/patch_ini.py)" "$(p /opt/YSFGateway/YSFGateway.ini)" "$(p /opt/xmode/legs/ysf/YSFGateway.ini)" "$SRC_DIR/legs/ysf/gateway.patch" || die "YSF gateway clone/patch failed -- see messages above"
python3 "$(p /opt/xmode/tools/patch_ini.py)" "$(p /opt/P25Gateway/P25Gateway.ini)" "$(p /opt/xmode/legs/p25/P25Gateway.ini)" "$SRC_DIR/legs/p25/gateway.patch" || die "P25 gateway clone/patch failed -- see messages above"
python3 "$(p /opt/xmode/tools/patch_ini.py)" "$(p /opt/NXDNGateway/NXDNGateway.ini)" "$(p /opt/xmode/legs/nxdn/NXDNGateway.ini)" "$SRC_DIR/legs/nxdn/gateway.patch" || die "NXDN gateway clone/patch failed -- see messages above"

say "Filling leg DMRGateway passwords from the main DMRGateway.ini (values never printed)"
XMODE_DIR="$(p /opt/xmode)" MAIN_GW="$MAIN_GW_INI" python3 - <<'PYEOF' || die "password fill failed"
import configparser, os, re, sys

def load(path):
    c = configparser.ConfigParser(interpolation=None, strict=False)
    c.optionxform = str
    try:
        c.read(path)
    except configparser.MissingSectionHeaderError:
        # Tolerate bare preamble lines (e.g. an "include =" directive
        # before the first section header, as dvs-generated inis have).
        c.read_string("[__preamble__]\n" + open(path).read())
    return c

main = load(os.environ["MAIN_GW"])
leg_path = os.path.join(os.environ["XMODE_DIR"], "legs", "dmr", "DMRGateway.ini")
text = open(leg_path).read()
filled = []
for sec in ("DMR Network 1", "DMR Network 2", "DMR Network 3"):
    if not main.has_section(sec):
        continue
    pw = main.get(sec, "Password", fallback="").strip().strip('"')
    if not pw:
        continue
    # The node ini style quotes password values: Password="..."
    pat = re.compile(r"(\[" + re.escape(sec) + r"\][^\[]*?^Password[ \t]*=[ \t]*)\"?__SET_[A-Z_]+__\"?",
                     re.M | re.S)
    text, n = pat.subn(lambda m: m.group(1) + '"' + pw + '"', text, count=1)
    if n:
        filled.append(sec)
if "__SET_" in text:
    print("ERROR: leg DMRGateway still has unfilled password markers", file=sys.stderr)
    sys.exit(1)
open(leg_path, "w").write(text)
print("  filled from main gateway:", ", ".join(filled) if filled else "(none needed)")
PYEOF

if [[ $REWIRE == 1 ]]; then
  say "Rewiring main Analog_Bridge [USRP] for the AGC shim (rx 34001->32021, tx 32001->34021)"
  SPEC=$(mktemp); AB_WORK=$(mktemp)
  printf 'R|USRP|rxPort|34001|32021\nR|USRP|txPort|32001|34021\n' > "$SPEC"
  cp -a "$MAIN_AB_INI" "$AB_WORK"
  python3 "$(p /opt/xmode/tools/patch_ini.py)" "$AB_WORK" "$MAIN_AB_INI" "$SPEC" || die "main AB rewire failed -- backup at $BACKUP_AB"
  rm -f "$SPEC" "$AB_WORK"
fi

say "Installing systemd units (leg stacks stay disabled -- on demand)"
for u in "$SRC_DIR"/units/*.service "$SRC_DIR"/usrp-agc/usrp-agc@.service; do
  install -m 0644 "$u" "$(p /etc/systemd/system/$(basename "$u"))"
done
$SYSTEMCTL daemon-reload
$SYSTEMCTL enable usrp-agc@main 2>/dev/null || true

say "Restarting the main Analog_Bridge onto its new ports, then starting the main AGC shim"
# Order matters: the shim binds the ports Analog_Bridge just vacated
# (34001); starting it first collides with the still-running bridge
# (found on the first live install, Nov 13 2026).
$SYSTEMCTL restart analog_bridge
$SYSTEMCTL start usrp-agc@main

say "Liveness"
FAIL=0
for u in usrp-agc@main analog_bridge; do
  if $SYSTEMCTL is-active --quiet "$u"; then echo "  active: $u"; else echo "  NOT ACTIVE: $u"; FAIL=1; fi
done
echo "  leg stacks installed, all stopped (they start with a bridge):"
echo "    analog-bridge-xmode-{dmr,ysf,p25,nxdn} mmdvm-bridge-xmode-{...}"
echo "    dmrgateway-xmode ysfgateway-xmode p25gateway-xmode nxdngateway-xmode usrp2m17-xmode"

cat > "$(p /opt/xmode/ROLLBACK.sh)" <<EOF
#!/usr/bin/env bash
# Rollback for the xmode install of $TS. Run as root.
set -x
$SYSTEMCTL stop usrp-agc@bridge usrp-agc@main 2>/dev/null
$SYSTEMCTL stop analog-bridge-xmode-dmr analog-bridge-xmode-ysf analog-bridge-xmode-p25 analog-bridge-xmode-nxdn mmdvm-bridge-xmode-dmr mmdvm-bridge-xmode-ysf mmdvm-bridge-xmode-p25 mmdvm-bridge-xmode-nxdn dmrgateway-xmode ysfgateway-xmode p25gateway-xmode nxdngateway-xmode usrp2m17-xmode 2>/dev/null
$SYSTEMCTL disable usrp-agc@main 2>/dev/null
rm -f /etc/systemd/system/{analog-bridge-xmode-dmr,analog-bridge-xmode-ysf,analog-bridge-xmode-p25,analog-bridge-xmode-nxdn,mmdvm-bridge-xmode-dmr,mmdvm-bridge-xmode-ysf,mmdvm-bridge-xmode-p25,mmdvm-bridge-xmode-nxdn,dmrgateway-xmode,ysfgateway-xmode,p25gateway-xmode,nxdngateway-xmode,usrp2m17-xmode,usrp-agc@}.service
$SYSTEMCTL daemon-reload
EOF
if [[ -n "$BACKUP_AB" ]]; then
  cat >> "$(p /opt/xmode/ROLLBACK.sh)" <<EOF
cp -a "$BACKUP_AB" "$MAIN_AB_INI"
$SYSTEMCTL restart analog_bridge
EOF
fi
cat >> "$(p /opt/xmode/ROLLBACK.sh)" <<EOF
rm -rf /opt/xmode /etc/USRP2M17-xmode.ini
echo "Rollback done. (Any /opt/xmode.bak.* tree from this install was left in place.)"
EOF
chmod 0755 "$(p /opt/xmode/ROLLBACK.sh)"
touch "$RPT_MARKER"

say "Done"
echo "  Main AGC shim is live. No bridge is up; use the dashboard"
echo "  Bridge card to tune legs and start a bridge."
echo "  Rollback for this install: sudo bash /opt/xmode/ROLLBACK.sh"
[[ $FAIL == 1 ]] && echo "  WARNING: a liveness check failed above -- check before use."
exit $FAIL
