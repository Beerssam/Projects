#!/usr/bin/env bash
# validate-dmr-configs.sh -- sanity-check a DMRGateway/MMDVM_Bridge/Analog_Bridge
# config set before it goes on a node. Catches the mistakes that fail silently:
# wrong localhost port pairing, bind conflicts, duplicate ESSIDs, missing
# rewrite rules, missing passwords, and AMBE audio port mismatches.
#
# The checks encode ground truth VERIFIED Oct 2026 against:
#   - DMRGateway source (g4klx/DMRGateway Conf.cpp, MMDVMNetwork.cpp) and its
#     distributed example ini: the MMDVM-client side is [General]
#     RptAddress/RptPort (127.0.0.1:62032); DMRGateway binds LocalPort (62031)
#     and accepts frames ONLY from RptPort. There is NO unnumbered
#     [DMR Network] section -- every [DMR Network N] is an upstream network.
#   - DVSwitch-distributed Analog_Bridge.ini / DVSwitch.ini (key names and
#     the crossed AMBE pairing).
#
# Usage: validate-dmr-configs.sh [config-dir]
#   config-dir defaults to ../nodes/kf0riz (relative to the script).
set -u
DIR="${1:-$(dirname "$0")/../nodes/kf0riz}"
DG="$DIR/DMRGateway.ini"
MM="$DIR/MMDVM_Bridge.ini"
AB="$DIR/Analog_Bridge.ini"
DVSW="$DIR/DVSwitch.ini"

pass=0; fail=0
ok()   { pass=$((pass+1)); echo "  ok: $1"; }
bad()  { fail=$((fail+1)); echo "  FAIL: $1"; }
warn() { echo "  warn: $1"; }

# ini <file> <section> <key> -> value (first match, trailing ';' comments stripped
# outside of quoted values)
ini() {
  awk -v sec="$2" -v key="$3" '
    /^\[.*\]/ { cur=$0; gsub(/^\[|\]$/, "", cur) }
    cur==sec && $0 ~ "^"key"[ \t]*=" {
      sub("^"key"[ \t]*=[ \t]*", "")
      if ($0 !~ /^"/) sub(/[ \t]*;.*$/, "")
      print; exit
    }
  ' "$1"
}

for f in "$DG" "$MM" "$AB"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 2; }
done
echo "checking $DIR"

# 1. DMRGateway must not have an unnumbered [DMR Network] section: current
#    DMRGateway parses it as an upstream network, not the localhost leg.
echo "- DMRGateway localhost leg:"
if grep -qE '^\[DMR Network\]' "$DG"; then
  bad "unnumbered [DMR Network] section present: current DMRGateway treats it as upstream network #1, not the localhost leg -- remove it"
else
  ok "no unnumbered [DMR Network] section"
fi

# 2. Localhost bridge leg pairing, verified against DMRGateway source:
#    DMRGateway binds [General] LocalPort; MMDVM_Bridge sends there.
#    DMRGateway only accepts frames from [General] RptPort, so MMDVM_Bridge
#    must bind that port as its Local.
dg_rpt=$(ini "$DG" "General" "RptPort");     [[ -z "$dg_rpt" ]] && dg_rpt=62032
dg_local=$(ini "$DG" "General" "LocalPort"); [[ -z "$dg_local" ]] && dg_local=62031
mm_port=$(ini "$MM" "DMR Network" "Port")
mm_local=$(ini "$MM" "DMR Network" "Local")
mm_addr=$(ini "$MM" "DMR Network" "Address")
echo "  DMRGateway [General]: RptPort=$dg_rpt LocalPort=$dg_local"
echo "  MMDVM_Bridge [DMR Network]: Address=$mm_addr Port=$mm_port Local=$mm_local"
[[ "$mm_port" == "$dg_local" ]] && ok "MMDVM_Bridge Port ($mm_port) == DMRGateway LocalPort ($dg_local): packets reach DMRGateway" \
  || bad "MMDVM_Bridge Port ($mm_port) != DMRGateway LocalPort ($dg_local): DMRGateway will never hear MMDVM_Bridge"
[[ "$mm_local" == "$dg_rpt" ]] && ok "MMDVM_Bridge Local ($mm_local) == DMRGateway RptPort ($dg_rpt): source check passes" \
  || bad "MMDVM_Bridge Local ($mm_local) != DMRGateway RptPort ($dg_rpt): DMRGateway drops the frames as 'invalid source'"
[[ "$mm_addr" == "127.0.0.1" ]] && ok "localhost address" \
  || warn "MMDVM_Bridge [DMR Network] Address=$mm_addr (expected 127.0.0.1 for a local DMRGateway)"

# 3. ESSID uniqueness across enabled DMRGateway network stanzas.
echo "- ESSID uniqueness:"
ids=$(grep -E '^[[:space:]]*Id=' "$DG" | sed 's/.*=//')
dup=$(echo "$ids" | sort | uniq -d)
[[ -z "$dup" ]] && ok "all DMR Id values unique ($(echo "$ids" | tr '\n' ' '))" \
  || bad "duplicate DMR Id: $dup (one login will kick the other)"

# 4. Every enabled [DMR Network N] stanza needs rewrite rules or it passes nothing.
echo "- rewrite rules per enabled network stanza:"
for n in 1 2 3 4 5; do
  en=$(ini "$DG" "DMR Network $n" "Enabled")
  [[ "$en" == "1" ]] || continue
  name=$(ini "$DG" "DMR Network $n" "Name")
  if grep -qE "^TGRewrite" <(awk -v sec="DMR Network $n" '
      /^\[.*\]/ { cur=$0; gsub(/^\[|\]$/, "", cur) } cur==sec { print }' "$DG"); then
    ok "[DMR Network $n] ($name) has TGRewrite rules"
  else
    bad "[DMR Network $n] ($name) enabled but has no TGRewrite rules: it will pass no traffic"
  fi
done

# 5. No SrcRewrite (caller radio IDs must pass through; TGRewrite auto-inverts
#    for return traffic -- verified in DMRGateway.cpp).
echo "- source-ID rewrites:"
if grep -qE '^SrcRewrite' "$DG"; then
  bad "SrcRewrite present in DMRGateway.ini: private calls from networks will be misrouted"
else
  ok "no SrcRewrite: caller IDs pass through unmodified"
fi

# 6. Password markers must be filled on the node (they must never be committed).
echo "- password markers:"
if grep -qE '__SET_[A-Z_]+__' "$DG" "$MM" "$AB" 2>/dev/null; then
  warn "unfilled __SET_...__ password marker(s) remain -- fill them on the node, never commit real secrets"
else
  ok "no __SET_...__ markers (passwords filled)"
fi

# 7. Analog_Bridge <-> MMDVM_Bridge AMBE audio pairing (verified against the
#    DVSwitch-distributed ini files -- crossed, not straight):
#      AB txPort (31103) -> MM rxPort (31103) ; AB rxPort (31100) <- MM txPort (31100)
#    MMDVM_Bridge's side lives in DVSwitch.ini [DMR], NOT in MMDVM_Bridge.ini.
echo "- AMBE audio:"
ab_tx=$(ini "$AB" "AMBE_AUDIO" "txPort"); ab_rx=$(ini "$AB" "AMBE_AUDIO" "rxPort")
if grep -qE '^(toPort|fromPort)[ \t]*=' "$AB"; then
  bad "Analog_Bridge.ini uses toPort/fromPort: real key names are txPort/rxPort (unknown keys are ignored)"
fi
if [[ -f "$DVSW" ]]; then
  mm_tx=$(ini "$DVSW" "DMR" "txPort"); mm_rx=$(ini "$DVSW" "DMR" "rxPort")
  echo "  Analog_Bridge [AMBE_AUDIO]: txPort=$ab_tx rxPort=$ab_rx | DVSwitch.ini [DMR]: txPort=$mm_tx rxPort=$mm_rx"
  [[ "$ab_tx" == "$mm_rx" && "$ab_rx" == "$mm_tx" ]] \
    && ok "AMBE audio ports pair correctly (crossed)" \
    || bad "AMBE audio port mismatch: need AB txPort == DVSwitch.ini rxPort and AB rxPort == DVSwitch.ini txPort"
else
  echo "  Analog_Bridge [AMBE_AUDIO]: txPort=$ab_tx rxPort=$ab_rx (no DVSwitch.ini in $DIR; stock file has txPort=31100/rxPort=31103)"
  [[ "$ab_tx" == "31103" && "$ab_rx" == "31100" ]] \
    && ok "Analog_Bridge AMBE ports match the stock DVSwitch.ini pairing" \
    || bad "Analog_Bridge AMBE ports differ from stock (txPort=31103 rxPort=31100) -- verify against DVSwitch.ini on the node"
fi

echo
echo "result: $pass passed, $fail failed"
exit $(( fail > 0 ))
