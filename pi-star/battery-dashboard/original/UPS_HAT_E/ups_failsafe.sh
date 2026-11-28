#!/bin/bash
# Read voltage
L_DEC=$(i2cget -y 1 0x2d 0x30 b)
H_DEC=$(i2cget -y 1 0x2d 0x31 b)
VOLTAGE_DEC=$(( (H_DEC * 256) + L_DEC ))

# Only trigger shutdown if voltage is critically low (e.g., < 3400mV) 
# and do NOT kill services manually. Let the system handle the poweroff.
if [ "$VOLTAGE_DEC" -lt 3400 ] && [ "$VOLTAGE_DEC" -gt 2500 ]; then
    echo "CRITICAL: Low Battery Detected ($VOLTAGE_DEC mV). Shutting down system." | wall
    sleep 5
    sudo poweroff
fi
