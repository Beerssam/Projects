#!/usr/bin/env bash
# net-status.sh -- privileged network-login status helper for the dvswitch
# dashboard.
#
# Why this exists (Oct 21 2026): Sam wants the dashboard SERVICES card to
# show whether BrandMeister / TGIF / KS-DMR are actually logged in, not
# just whether processes run. DMRGateway logs only to the systemd journal,
# and the journal is NOT readable by www-data ("No journal files were
# opened due to insufficient permissions" -- verified on the node). Same
# pattern as gain-set.sh / mode-switch.sh: www-data may run ONLY this
# script via sudo; it inspects the journal and reports verdicts.
#
# For each network it finds the LAST journal line that carries the
# network's Name and a login verdict -- "Logged into the master
# successfully" (connected) vs a failure phrase (down). The timestamp of
# that line is converted from the log's UTC to node-local time so the page
# can show "Connected · 18:09". No matching line at all -> unknown (e.g.
# the journal rotated past the last login).
#
# Usage: sudo net-status.sh        (takes no arguments)
# Env overrides (for testing): NET_STATUS_SRC (file to read instead of
# the journal).
# Stdout (parsed by the CGI):
#   BM=connected 18:09
#   TGIF=down 21:03
#   KSDMR=unknown

set -u

if [[ -n "${NET_STATUS_SRC:-}" ]]; then
  JOURNAL=$(cat "$NET_STATUS_SRC" 2>/dev/null)
else
  JOURNAL=$(journalctl -u dmrgateway --no-pager -n 6000 -o cat 2>/dev/null)
fi

verdict() {
  # $1 = network Name as it appears in the journal (BM_3103, ...)
  local name="$1" line ts state
  line=$(printf '%s\n' "$JOURNAL" | grep -F "$name" \
    | grep -iE "logged into|failed|timed out|timeout|refused|unreachable|disconnect|lost|closed" \
    | tail -1)
  if [[ -z "$line" ]]; then
    printf 'unknown'
    return
  fi
  if printf '%s' "$line" | grep -qi "logged into"; then
    state="connected"
  else
    state="down"
  fi
  ts=$(printf '%s' "$line" | grep -oE "[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}" | head -1)
  if [[ -n "$ts" ]]; then
    printf '%s %s' "$state" "$(date -d "$ts UTC" +%H:%M 2>/dev/null)"
  else
    printf '%s' "$state"
  fi
}

printf 'BM=%s\n'    "$(verdict BM_3103)"
printf 'TGIF=%s\n'  "$(verdict TGIF_Network)"
printf 'KSDMR=%s\n' "$(verdict KSDMR)"
exit 0
