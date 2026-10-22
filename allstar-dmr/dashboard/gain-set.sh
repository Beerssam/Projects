#!/usr/bin/env bash
# gain-set.sh -- privileged audio-gain helper for the dvswitch dashboard.
#
# Root-cause fix (Oct 21 2026): the dashboard's Audio Levels sliders never
# actually saved. do_gain in the CGI ran `sudo sed -i`, `sudo tee -a` and
# `sudo systemctl restart` as www-data, but the sudoers rule only ever
# permitted dvswitch.sh and mode-switch.sh -- every write was refused, the
# CGI swallowed the error and reported success, and the sliders snapped
# back to the ini values (tlvGain 0.25 / usrpGain 4.00) on every refresh.
# Verified on the node: the ini held exactly one gain line each, untouched.
# This helper is the single privileged write path, same pattern as
# mode-switch.sh: www-data may run ONLY this script via sudo.
#
# Usage: sudo gain-set.sh tlv|usrp <value>    (value 0.0 - 5.0)
# Env overrides (for testing): ANALOG_INI, SYSTEMCTL
# Exit: 0 = value written, analog_bridge restarted, read-back verified;
#       1 = write/restart/verify failure; 2 = bad usage.
# Stdout (parsed by the CGI): "tlv=<val>" and "usrp=<val>" read back from
# the ini after the write, plus optionally "note=<text>".

set -u
ANALOG_INI="${ANALOG_INI:-/opt/Analog_Bridge/Analog_Bridge.ini}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"

WHICH="${1:-}"
VALUE="${2:-}"
case "$WHICH" in
  tlv)  KEY="tlvGain" ;;
  usrp) KEY="usrpGain" ;;
  *) echo "note=usage: gain-set.sh tlv|usrp <value>"; exit 2 ;;
esac
if ! [[ "$VALUE" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "note=invalid value: $VALUE"; exit 2
fi
if ! awk -v v="$VALUE" 'BEGIN{exit !(v+0 >= 0 && v+0 <= 5)}'; then
  echo "note=value out of range 0.0-5.0: $VALUE"; exit 2
fi
if [[ ! -r "$ANALOG_INI" ]]; then
  echo "note=not readable: $ANALOG_INI"; exit 1
fi

read_gain() {
  # $1 = key -> numeric value of the first ^key line, or empty
  awk -v key="$1" '
    $0 ~ "^" key "[ \t]*=" {
      v = $0
      sub(/^[^=]*=[ \t]*/, "", v)
      sub(/[ \t;].*$/, "", v)
      if (v ~ /^[0-9]+(\.[0-9]+)?$/) { print v; exit }
    }' "$ANALOG_INI" 2>/dev/null
}

set_gain() {
  # $1 = key, $2 = value. Rewrites the FIRST ^key line's value in place
  # (trailing comment preserved), drops any later duplicate ^key lines
  # (targeted single-key dedup only), appends the key if absent.
  local key="$1" val="$2" tmp
  tmp=$(mktemp) || return 1
  if ! awk -v key="$key" -v val="$val" '
    $0 ~ "^" key "[ \t]*=" {
      if (done) next
      sub(/=[ \t]*[0-9]+(\.[0-9]+)?/, "= " val)
      done = 1
      print
      next
    }
    { print }
    END { if (!done) print key " = " val }
  ' "$ANALOG_INI" > "$tmp"; then
    rm -f "$tmp"; return 1
  fi
  if ! cat "$tmp" > "$ANALOG_INI"; then
    rm -f "$tmp"; return 1
  fi
  rm -f "$tmp"
  return 0
}

if ! set_gain "$KEY" "$VALUE"; then
  echo "note=write failed on $ANALOG_INI"; exit 1
fi

if ! "$SYSTEMCTL" restart analog_bridge 2>/dev/null; then
  echo "note=analog_bridge restart failed"; exit 1
fi

got=$(read_gain "$KEY")
if ! awk -v a="$got" -v b="$VALUE" 'BEGIN{exit !(a+0 == b+0)}'; then
  echo "note=read-back mismatch: wrote $VALUE, ini has ${got:-<none>}"
  exit 1
fi

printf 'tlv=%s\n' "$(read_gain tlvGain)"
printf 'usrp=%s\n' "$(read_gain usrpGain)"
exit 0
