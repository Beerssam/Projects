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
if is_num "$PCT" && is_num "$MV"; then echo "$NOW $PCT $MV $MA $STATE_KEY" >> "$HISTORY"; fi
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

# --- on-battery session (from the history log) --------------------------------------
SESSION_HTML=""
if [ "$ON_BATT" = "true" ] && [ -f "$HISTORY" ]; then
    SESS=$(awk -v now="$(date +%s)" '
        ($5=="discharging" || $5=="low") { if (!b) { s=$1; sp=$2; b=1 } }
        ($5!="discharging" && $5!="low") { b=0 }
        END { if (b) { d=now-s; printf "%dh %02dm|%d", int(d/3600), int((d%3600)/60), sp } }' "$HISTORY")
    if [ -n "$SESS" ]; then
        S_DUR=${SESS%%|*}; S_STARTPCT=${SESS##*|}
        S_DROP=$((S_STARTPCT - PCT)); [ "$S_DROP" -lt 0 ] && S_DROP=0
        SESSION_HTML="<div style='border-top:1px solid #1e293b;margin-top:10px;padding-top:10px;'><div class='lbl' style='color:#38bdf8;'>ON BATTERY &middot; ${S_DUR}</div><div style='font-size:13px;color:#94a3b8;margin-top:3px;'>Down ${S_DROP}% this session</div></div>"
    fi
fi

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

# --- radio state: last heard from today's MMDVM log ------------------------------
RADIO_MODE="--"; RADIO_TXT="No activity logged"; RADIO_SUB=""
MLOG=$(ls -t /var/log/pi-star/MMDVM-*.log 2>/dev/null | head -1)
if [ -n "$MLOG" ]; then
    LH=$(grep -E 'received (RF|network)' "$MLOG" 2>/dev/null | tail -1)
    if [ -n "$LH" ]; then
        RADIO_MODE=$(echo "$LH" | grep -oE '(DMR|YSF|P25|NXDN|D-Star|M17)' | head -1)
        LCALL=$(echo "$LH" | sed -n 's/.*from \([A-Za-z0-9\/]*\).*/\1/p')
        LTGT=$(echo "$LH" | sed -n 's/.* to \([^,]*\).*/\1/p')
        LTIME=$(echo "$LH" | grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}' | head -1 | cut -d: -f1,2)
        if [ -n "$LCALL" ]; then
            RADIO_TXT="${LCALL} &rarr; ${LTGT}"
            LT_LOC=$(date -d "$LTIME UTC" +"%H:%M %Z" 2>/dev/null)
            RADIO_SUB="<div style='font-size:12px;color:#94a3b8;margin-top:3px;'>UTC &middot; ${LTIME}</div><div style='font-size:12px;color:#94a3b8;'>LOCAL &middot; ${LT_LOC}</div>"
        fi
        [ -z "$RADIO_MODE" ] && RADIO_MODE="--"
    fi
fi

# --- power health (Pi's own throttle/under-voltage flags) + uptime ----------------
THR=$(vcgencmd get_throttled 2>/dev/null | grep -oE '0x[0-9a-fA-F]+')
if [ -n "$THR" ]; then
    THR_DEC=$((THR))
    if [ $((THR_DEC & 1)) -ne 0 ] || [ $((THR_DEC & 4)) -ne 0 ]; then SUPPLY_TXT="<span style='color:#ef4444'>Under-voltage now</span>"
    elif [ "$THR_DEC" -ne 0 ]; then SUPPLY_TXT="<span style='color:#eab308'>Sagged earlier</span>"
    else SUPPLY_TXT="<span style='color:#22c55e'>OK</span>"; fi
else SUPPLY_TXT="--"; fi
UPT_TXT=$(awk '{d=int($1/86400); h=int(($1%86400)/3600); m=int(($1%3600)/60); if (d>0) printf "%dd %dh", d, h; else printf "%dh %dm", h, m}' /proc/uptime)

# --- network identity ---------------------------------------------------------------
SSID=$(iwgetid wlan0 -r 2>/dev/null)
[ -z "$SSID" ] && SSID=$(wpa_cli -i wlan0 status 2>/dev/null | sed -n 's/^ssid=//p')
SSID=$(echo "$SSID" | tr -cd 'A-Za-z0-9 _.-')
[ -z "$SSID" ] && SSID="--"
ZT_STAT=$(sudo -n /usr/sbin/zerotier-cli info 2>/dev/null | awk '{print $5}')
[ -z "$ZT_STAT" ] && ZT_STAT=$(/usr/sbin/zerotier-cli info 2>/dev/null | awk '{print $5}')
[ -z "$ZT_STAT" ] && ZT_STAT=$(zerotier-cli info 2>/dev/null | awk '{print $5}')
ZT_SUFFIX=""; [ "$ZT_STAT" = "ONLINE" ] && ZT_SUFFIX=" &middot; ONLINE"

# --- memory ----------------------------------------------------------------------
MEM_PCT=$(free -m | awk 'NR==2 {printf "%d", $3/$2*100}')
MEM_TOT=$(free -m | awk 'NR==2 {print $2}')

# --- gateway status dots -----------------------------------------------------------
GW_DOTS=""
for pair in "DMR:dmrgateway" "YSF:ysfgateway" "P25:p25gateway" "NXDN:nxdngateway"; do
    lbl=${pair%%:*}; svc=${pair##*:}
    if systemctl cat "$svc" >/dev/null 2>&1; then
        if systemctl is-active --quiet "$svc" 2>/dev/null; then dot="#22c55e"; else dot="#ef4444"; fi
        GW_DOTS="${GW_DOTS}<span style='margin-right:12px;'><span style='color:${dot}'>&#9679;</span> ${lbl}</span>"
    fi
done
GW_STRIP=""
[ -n "$GW_DOTS" ] && GW_STRIP="<div style='border-top:1px solid #1e293b;margin-top:10px;padding-top:10px;'><div class='lbl'>GATEWAYS</div><div style='font-size:13px;margin-top:5px;'>${GW_DOTS}</div></div>"

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
<title>Hotspot Dashboard</title>
<style>
  body { background:#0b1220; color:#e2e8f0; font-family:ui-monospace,Menlo,Consolas,monospace; margin:0; padding:18px; }
  .card { background:#0f172a; border:1px solid #1e293b; border-radius:10px; max-width:560px; margin:0 auto; padding:22px 22px 16px; }
  .hd { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e293b; padding-bottom:12px; }
  .hd-r { display:flex; flex-direction:column; align-items:flex-end; gap:6px; }
  .title { font-size:clamp(17px, 5.2vw, 27px); font-weight:700; letter-spacing:2px; white-space:nowrap; color:#f1f5f9; }
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
  @media (min-width: 700px) { .card { max-width:680px; } }
  @media (min-width: 1000px) {
    body { padding:36px; }
    .card { max-width:920px; padding:34px 38px 24px; }
    .title { font-size:27px; } .sub { font-size:13px; }
    .lbl { font-size:13px; }
    .big { font-size:88px; } .big .pc { font-size:40px; }
    .gauge { height:14px; } .trend { height:38px; }
    .grid { grid-template-columns:1fr 1fr 1fr; }
    .cell .k { font-size:12px; } .cell .v { font-size:29px; }
    .ips { font-size:14px; } .ft { font-size:12px; }
  }
</style>
</head>
<body>
<div class="card">
  <div class="hd">
    <div><div class="title">HOTSPOT DASHBOARD</div><div class="sub">KF0RIZ &middot; MOBILE WPSD</div></div>
    <div class="hd-r"><span class="pill" style="color:${PILL_COLOR};border-color:${PILL_COLOR}">&#9679; ${STATE}</span><div class="sync">SYNC ${SYNC_TIME}</div></div>
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
  </div>${SESSION_HTML}
  <div style="border-top:1px solid #1e293b;margin-top:10px;padding-top:10px;">
    <div class="lbl">RADIO &middot; ${RADIO_MODE}</div>
    <div style="font-size:15px;margin-top:4px;">${RADIO_TXT}</div>${RADIO_SUB}
  </div>${GW_STRIP}
  <div class="grid">
    <div class="cell"><div class="k">WI-FI SIGNAL</div><div class="v">${RSSI_TXT}</div><div class="unit">${SSID}</div></div>
    <div class="cell"><div class="k">LATENCY</div><div class="v">${LAT_TXT}</div></div>
    <div class="cell"><div class="k">MMDVM</div><div class="v">${SVC_TXT}</div></div>
    <div class="cell"><div class="k">CPU LOAD</div><div class="v">${LOAD_TXT}</div></div>
    <div class="cell"><div class="k">TEMPERATURE</div><div class="v">${TEMP_C}&deg;C <span class="unit">/ ${TEMP_F}&deg;F</span></div></div>
    <div class="cell"><div class="k">STORAGE</div><div class="v">${DISK_PCT}<span class="unit">% full</span></div></div>
    <div class="cell"><div class="k">SUPPLY</div><div class="v">${SUPPLY_TXT}</div></div>
    <div class="cell"><div class="k">UPTIME</div><div class="v">${UPT_TXT}</div></div>
    <div class="cell"><div class="k">MEMORY</div><div class="v">${MEM_PCT}<span class="unit">% of ${MEM_TOT} MB</span></div></div>
  </div>
  <div class="ips">
    <div><span class="k">PUBLIC</span>${PUBLIC_IP}</div>
    <div><span class="k">ZEROTIER</span>${ZT_IP}${ZT_SUFFIX}</div>
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
