#!/bin/bash
# generate_webpage_v2.sh -- Hotspot Command battery/status page, v2
# Lives in ~/UPS_HAT_E/ (survives WPSD updates). Writes:
#   /var/www/battery_data/index.html   (the page)
#   /var/www/battery_data/battery.json (machine-readable, for monitoring)
#   ~/UPS_HAT_E/battery_history.log    (epoch pct mv, for the 24h trend)
# v1 (generate_webpage.sh) is untouched; rollback = point cron back at it.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
HOME_DIR="/home/pi-star/UPS_HAT_E"
OUT_DIR="/var/www/battery_data"
HISTORY="$HOME_DIR/battery_history.log"
ZT_IP="10.167.65.201"

# --- helpers ---------------------------------------------------------------
rd_b() { i2cget -y 1 0x2d "$1" b 2>/dev/null; }          # byte register
rd_w() { i2cget -y 1 0x2d "$1" w 2>/dev/null; }          # word register
is_num() { case "$1" in ''|*[!0-9-]*) return 1;; *) return 0;; esac; }

# --- battery (skip I2C polling in the 00:46-04:14 maintenance window) -----
CURRENT_TIME=$(date +%H%M)
IN_WINDOW=0
if [ "$CURRENT_TIME" -gt "0045" ] && [ "$CURRENT_TIME" -lt "0415" ]; then IN_WINDOW=1; fi

PCT=""; MV=""; MA=""; TTE=""; TTF=""
if [ "$IN_WINDOW" -eq 0 ]; then
    PCT_HEX=$(rd_b 0x24); [ -n "$PCT_HEX" ] && PCT=$((PCT_HEX))
    VL=$(rd_b 0x30); VH=$(rd_b 0x31)
    if [ -n "$VL" ] && [ -n "$VH" ]; then MV=$(( (VH * 256) + VL )); fi
    # 0x20-block words (per batteryTray.py): current at 0x22 (signed mA),
    # time-to-empty at 0x28, time-to-full at 0x2a. Sanity-checked; the
    # v1-proven byte reads above stay authoritative for pct/voltage.
    IW=$(rd_w 0x22)
    if [ -n "$IW" ]; then
        MA=$((IW)); [ "$MA" -ge 32768 ] && MA=$((MA - 65536))
        if [ "$MA" -gt 5000 ] || [ "$MA" -lt -5000 ]; then MA=""; fi
    fi
    EW=$(rd_w 0x28); if is_num "$EW" && [ "$EW" -ge 0 ] && [ "$EW" -le 3000 ]; then TTE=$EW; fi
    FW=$(rd_w 0x2a); if is_num "$FW" && [ "$FW" -ge 0 ] && [ "$FW" -le 3000 ]; then TTF=$FW; fi
fi

# --- charge state ------------------------------------------------------------
STATE="Syncing..."; STATE_KEY="syncing"; PILL_COLOR="#eab308"; ON_BATT="false"; ESTIMATE="N/A"
if is_num "$PCT" && is_num "$MV"; then
    if is_num "$MA" && [ "$MA" -gt 30 ]; then
        STATE="Charging"; STATE_KEY="charging"; PILL_COLOR="#22c55e"
    elif is_num "$MA" && [ "$MA" -lt -30 ]; then
        STATE="On Battery"; STATE_KEY="discharging"; PILL_COLOR="#38bdf8"; ON_BATT="true"
    elif [ "$PCT" -ge 99 ]; then
        STATE="Full"; STATE_KEY="full"; PILL_COLOR="#22c55e"
    elif is_num "$MA"; then
        STATE="Wall Power"; STATE_KEY="full"; PILL_COLOR="#22c55e"
    elif [ "$MV" -ge 4080 ]; then
        STATE="Wall Power (Charged)"; STATE_KEY="full"; PILL_COLOR="#22c55e"
    elif [ "$MV" -le 3600 ]; then
        STATE="Low Battery"; STATE_KEY="low"; PILL_COLOR="#ef4444"; ON_BATT="true"
    else
        STATE="On Battery"; STATE_KEY="discharging"; PILL_COLOR="#38bdf8"; ON_BATT="true"
    fi
    # runtime estimate: chip registers first, v1 linear math as fallback
    if [ "$STATE_KEY" = "charging" ] && is_num "$TTF"; then
        ESTIMATE="full in ~$((TTF / 60))h $((TTF % 60))m"
    elif [ "$STATE_KEY" = "discharging" ] && is_num "$TTE"; then
        ESTIMATE="$((TTE / 60))h $((TTE % 60))m left"
    elif [ "$STATE_KEY" = "full" ]; then
        ESTIMATE="Fully charged"
    elif [ "$STATE_KEY" = "low" ]; then
        ESTIMATE="Charge required"
    elif [ "$STATE_KEY" = "discharging" ]; then
        TM=$(( (PCT * 1080) / 100 )); ESTIMATE="$((TM / 60))h $((TM % 60))m left"
    fi
fi
LOW="false"
if [ "$ON_BATT" = "true" ] && is_num "$PCT" && [ "$PCT" -lt 25 ]; then LOW="true"; fi
PCT_TXT="N/A"; is_num "$PCT" && PCT_TXT="$PCT"
MV_TXT="N/A";  is_num "$MV" && MV_TXT=$(printf '%s mV' "$MV")
MA_TXT="";     is_num "$MA" && MA_TXT=$(printf ' &middot; %+d mA' "$MA")

# --- history + 24h trend ------------------------------------------------------
NOW=$(date +%s)
if is_num "$PCT" && is_num "$MV"; then echo "$NOW $PCT $MV" >> "$HISTORY"; fi
[ -f "$HISTORY" ] && tail -n 2016 "$HISTORY" > "$HISTORY.tmp" && mv "$HISTORY.tmp" "$HISTORY"
TREND_BARS=""; TMIN=""; TMAX=""
if [ -f "$HISTORY" ]; then
    read TMIN TMAX TREND_BARS <<EOF
$(awk -v now="$NOW" '
    $1 >= now-86400 { n++; if (min=="" || $2<min) min=$2; if (max=="" || $2>max) max=$2;
        b=int((now-$1)/6171); if (b>13) b=13; s[13-b]+=$2; c[13-b]++ }
    END { if (n==0) { print "- - "; exit }
        printf "%d %d ", min, max;
        for (i=0;i<14;i++) { if (c[i]>0) { h=int(s[i]/c[i]); if (h<5) h=5;
            col=(i==13)?"#38bdf8":"#334155";
            printf "<div style=\"flex:1;background:%s;height:%d%%;\"></div>", col, h }
          else printf "<div style=\"flex:1;background:#1e293b;height:5%%;\"></div>" }
    }' "$HISTORY")
EOF
fi
[ -z "$TREND_BARS" ] && TREND_BARS="<div style='flex:1;background:#1e293b;height:5%;'></div>"
TREND_TXT="NO DATA YET"
is_num "$TMIN" && TREND_TXT="MIN ${TMIN}% &middot; MAX ${TMAX}%"

# --- system stats ---------------------------------------------------------------
TEMP_RAW=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
TEMP_C=$((TEMP_RAW / 1000)); TEMP_F=$(( (TEMP_C * 9 / 5) + 32 ))
RSSI_RAW=$(awk 'NR==3 {print $4}' /proc/net/wireless 2>/dev/null | tr -d '.')
if is_num "$RSSI_RAW"; then RSSI_TXT="${RSSI_RAW} <span class='unit'>dBm</span>"; else RSSI_TXT="Disconnected"; fi
IP_ADDR=$(ip -4 addr show wlan0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1)
[ -z "$IP_ADDR" ] && IP_ADDR="No Connection"
PUBLIC_IP=$(curl -4 -s --max-time 3 ifconfig.me 2>/dev/null)
[ -z "$PUBLIC_IP" ] && PUBLIC_IP="Offline"
PING_T=$(ping -c 1 -W 2 8.8.8.8 2>/dev/null | grep -o 'time=[0-9.]*' | cut -d= -f2 | cut -d. -f1)
if is_num "$PING_T"; then LAT_TXT="${PING_T} <span class='unit'>ms</span>"; else LAT_TXT="Timeout"; fi
LOAD_TXT=$(awk '{print $1}' /proc/loadavg)
if systemctl is-active --quiet mmdvmhost 2>/dev/null; then SVC_TXT="<span style='color:#22c55e'>Active</span>"; else SVC_TXT="<span style='color:#ef4444'>Down</span>"; fi
DISK_PCT=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
SYNC_TIME=$(date +"%H:%M")

# --- battery.json (monitoring) ---------------------------------------------------
cat > "$OUT_DIR/battery.json" <<JSON
{"pct": ${PCT:-null}, "mv": ${MV:-null}, "state": "${STATE_KEY}", "on_battery": ${ON_BATT}, "low": ${LOW}, "ts": "$(date -Iseconds)"}
JSON

# --- the page ---------------------------------------------------------------------
cat <<WEB | tee "$OUT_DIR/index.html" > /dev/null
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta http-equiv="refresh" content="60">
<title>Hotspot Command</title>
<style>
  body { background:#0b1220; color:#e2e8f0; font-family:ui-monospace,Menlo,Consolas,monospace; margin:0; padding:18px; }
  .card { background:#0f172a; border:1px solid #1e293b; border-radius:10px; max-width:560px; margin:0 auto; padding:22px 22px 16px; }
  .hd { display:flex; justify-content:space-between; align-items:baseline; border-bottom:1px solid #1e293b; padding-bottom:12px; }
  .title { font-size:19px; font-weight:700; letter-spacing:2.5px; color:#f1f5f9; }
  .sub { font-size:11px; letter-spacing:1.5px; color:#64748b; margin-top:3px; }
  .pill { font-size:11px; letter-spacing:1px; border:1px solid; border-radius:999px; padding:3px 10px; }
  .sync { font-size:11px; color:#64748b; margin-top:6px; text-align:right; }
  .lbl { font-size:11px; letter-spacing:2px; color:#94a3b8; }
  .big { font-size:52px; font-weight:700; color:#f1f5f9; line-height:1; }
  .big .pc { font-size:26px; color:#94a3b8; }
  .gauge { height:10px; background:#1e293b; border-radius:5px; margin-top:10px; overflow:hidden; }
  .gauge div { height:100%; background:#38bdf8; border-radius:5px; }
  .trend { display:flex; gap:3px; align-items:flex-end; height:26px; margin-top:14px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; column-gap:22px; margin-top:8px; }
  .cell { border-top:1px solid #1e293b; padding:10px 0; }
  .cell .k { font-size:10px; letter-spacing:2px; color:#94a3b8; }
  .cell .v { font-size:21px; margin-top:3px; }
  .unit { font-size:12px; color:#94a3b8; }
  .ips { border-top:1px solid #1e293b; margin-top:6px; padding-top:12px; font-size:12px; line-height:2; }
  .ips .k { display:inline-block; width:92px; color:#64748b; letter-spacing:1px; }
  .ft { border-top:1px solid #1e293b; margin-top:12px; padding-top:12px; font-size:11px; color:#64748b; line-height:1.7; }
</style>
</head>
<body>
<div class="card">
  <div class="hd">
    <div><div class="title">HOTSPOT COMMAND</div><div class="sub">KF0RIZ &middot; MOBILE WPSD</div></div>
    <div><span class="pill" style="color:${PILL_COLOR};border-color:${PILL_COLOR}">&#9679; ${STATE}</span><div class="sync">SYNC ${SYNC_TIME}</div></div>
  </div>
  <div style="padding:16px 0 6px;">
    <div style="display:flex;justify-content:space-between;align-items:baseline;">
      <div class="lbl">BATTERY</div><div style="font-size:12px;color:#94a3b8;">${MV_TXT}${MA_TXT}</div>
    </div>
    <div style="display:flex;align-items:baseline;gap:10px;margin-top:2px;">
      <div class="big">${PCT_TXT}<span class="pc">%</span></div>
      <div style="font-size:13px;color:#38bdf8;">${ESTIMATE}</div>
    </div>
    <div class="gauge"><div style="width:${PCT_TXT}%;"></div></div>
    <div class="trend">${TREND_BARS}</div>
    <div style="display:flex;justify-content:space-between;font-size:10px;color:#64748b;margin-top:4px;"><span>24H TREND</span><span>${TREND_TXT}</span></div>
  </div>
  <div class="grid">
    <div class="cell"><div class="k">WI-FI SIGNAL</div><div class="v">${RSSI_TXT}</div></div>
    <div class="cell"><div class="k">LATENCY</div><div class="v">${LAT_TXT}</div></div>
    <div class="cell"><div class="k">MMDVM</div><div class="v">${SVC_TXT}</div></div>
    <div class="cell"><div class="k">CPU LOAD</div><div class="v">${LOAD_TXT}</div></div>
    <div class="cell"><div class="k">TEMPERATURE</div><div class="v">${TEMP_C}&deg;C <span class="unit">/ ${TEMP_F}&deg;F</span></div></div>
    <div class="cell"><div class="k">STORAGE</div><div class="v">${DISK_PCT}<span class="unit">% full</span></div></div>
  </div>
  <div class="ips">
    <div><span class="k">PUBLIC</span>${PUBLIC_IP}</div>
    <div><span class="k">ZEROTIER</span>${ZT_IP}</div>
    <div><span class="k">LOCAL</span>${IP_ADDR}</div>
  </div>
  <div class="ft"><div style="color:#94a3b8;">pi-star.freeddns.org/battery/</div><div>UPDATED EVERY 5 MIN</div></div>
</div>
</body>
</html>
WEB

# --- low-voltage failsafe (kept from v1) -------------------------------------------
if is_num "$MV" && [ "$MV" -lt 3400 ] && [ "$MV" -gt 2500 ]; then
    echo "CRITICAL WARNING: Battery depleted to ${MV}mV." | wall
    sleep 5
    sudo poweroff
fi
