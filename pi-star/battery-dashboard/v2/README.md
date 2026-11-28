# Battery Dashboard v2

The modernized rebuild of Sam's hotspot battery page. The v1 original in
`../original/` is frozen and untouched; v2 deploys alongside it and can
be rolled back by pointing cron back at v1.

## What v2 fixes and adds

- Real charge state from the UPS chip's current register (sign of mA)
  instead of guessing from voltage; chip time-to-empty / time-to-full
  registers for the runtime estimate, v1 linear math as fallback.
- Latency parsed from ping's `time=` value (v1 showed negative ms).
- 24-hour battery trend (history logged every run) with min/max.
- `battery.json` written next to the page for monitoring — an Uptime
  Kuma keyword monitor alerts on Telegram when the hotspot is on
  battery under 25%.
- Refresh every 5 minutes (v1 was 15). No remount tricks — the v1-era
  crashes traced to the remount-ro wrapper, which v2 never does.
- Redesigned page: same dark slate + sky blue identity, instrument
  grid, gauge bar, status pill. Single self-contained page, system
  fonts, no external assets.

## Update-proofing

Everything lives in `~/UPS_HAT_E/` on the hotspot, which WPSD updates
don't touch. The only system wiring is one cron file; `install.sh`
(re)creates it, backs up and retires the v1 schedulers, and installs a
daily self-check in the user crontab that restores the wiring if a
WPSD update ever wipes it. This folder is the GitHub mirror of the
deployed files.

## Files

- `generate_webpage_v2.sh` — the generator (runs every 5 min).
- `install.sh` — wiring installer / self-check.
