#!/usr/bin/env bash
# Render templates/*.ini from vars.sh into output/.
# Needs envsubst (Debian: sudo apt install gettext-base).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f vars.sh ]]; then
  echo "Copy vars.example.sh to vars.sh and fill it in first." >&2
  exit 1
fi
if ! command -v envsubst >/dev/null 2>&1; then
  echo "envsubst not found. Install it: sudo apt install gettext-base" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source vars.sh
set +a

mkdir -p output
for t in templates/*.ini; do
  out="output/$(basename "$t")"
  envsubst < "$t" > "$out"
  echo "wrote $out"
done

echo
echo "Review output/, then install to /opt/... and restart in order:"
echo "  DMRGateway -> MMDVM_Bridge -> Analog_Bridge (Asterisk stays running)"
