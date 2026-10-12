#!/usr/bin/env bash
# Copy to vars.sh and fill in. vars.sh is gitignored - never commit real credentials.
# Get your DMR ID (CCS7) at radioid.net.

# Your amateur callsign (no SSID)
CALLSIGN="YOURCALL"

# Base DMR ID, e.g. 1234567
DMR_ID="1234567"

# Location string for the [Info] section, e.g. "Shawnee, KS"
LOCATION="Your town, ST"

# --- BrandMeister (DMR Network 1) ---
# Nearest master, e.g. 3104.master.brandmeister.network
BM_MASTER="3104.master.brandmeister.network"
# Short label used in the config (no dots)
BM_MASTER_SHORT="3104"
# Hotspot security password: brandmeister.network -> SelfCare -> Security.
# The old default "passw0rd" is REJECTED - you must set your own.
BM_PASSWORD="put-your-bm-hotspot-password-here"
# Unique ID for the BM connection: base ID + ESSID suffix
BM_ESSID="123456701"

# --- TGIF (DMR Network 2) ---
# Hotspot password from your tgif.network dashboard
TGIF_PASSWORD="put-your-tgif-password-here"
# Unique ID for the TGIF connection: base ID + different ESSID suffix
TGIF_ESSID="123456702"
