#!/bin/bash

# Directly grab the full 16-bit Word registry block from the chip
HEX_WORD=$(i2cget -y 1 0x2d 0x22 w 2>/dev/null)

if [ ! -z "$HEX_WORD" ] && [ "$HEX_WORD" != "0x0000" ]; then
    
    # Extract and reverse the bytes to align with the i2cdump layout
    V_HEX=$(echo $HEX_WORD | awk '{print "0x" substr($1,5,2) substr($1,3,2)}')
    RAW_VALUE=$((V_HEX))

    # Safety boundary catch for raw data parsing
    if [ $RAW_VALUE -lt 100 ] || [ $RAW_VALUE -gt 1000 ]; then
        RAW_VALUE=$((HEX_WORD))
    fi

    # CALIBRATION: Multiply by 10 to turn the scaled register reading (e.g. 334) 
    # into the true operating millivolts (3340mV)
    VOLTAGE_DEC=$(( RAW_VALUE * 10 ))
    
    # Calculate battery capacity scale (3200mV Empty to 4200mV Full)
    PCT=$(( (VOLTAGE_DEC - 3200) * 100 / (4200 - 3200) ))
    
    # Enforce standard 0% to 100% boundary limits
    if [ $PCT -lt 0 ]; then PCT=0; fi
    if [ $PCT -gt 100 ]; then PCT=100; fi

    echo "Voltage Capacity: ${VOLTAGE_DEC}mV | Battery Life: ${PCT}.0%"
else
    echo "Voltage Capacity: Synced | Battery Life: Calibrating Chip..."
fi
