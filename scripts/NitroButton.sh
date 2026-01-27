#!/bin/bash

# NitroButton Service
# Listens for the Nitro key (KEY_PROG3 / code 425) and delegates to long_press_handler.sh.

# Path to the handler script (Prioritize local project script for portability)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HANDLER_SCRIPT="$SCRIPT_DIR/long_press_handler.sh"

if [ ! -f "$HANDLER_SCRIPT" ]; then
    # Fallback to user custom path or system path
    HANDLER_SCRIPT="$HOME/.config/hypr/custom/scripts/long_press_handler.sh"
    if [ ! -f "$HANDLER_SCRIPT" ]; then
        HANDLER_SCRIPT="/opt/acersense/keyboard/long_press_handler.sh"
    fi
fi

# Find keyboard device
DEVICE=$(grep -E -A 4 'Handlers|EV=' /proc/bus/input/devices | grep -B 4 'EV=120013' | grep -o 'event[0-9]\+' | head -n 1)

if [ -z "$DEVICE" ]; then
    DEVICE=$(grep -A 5 -B 5 "keyboard\|Keyboard" /proc/bus/input/devices | grep -m 1 "event" | sed 's/.*event\([0-9]\+\).*/event\1/')
fi

if [ -z "$DEVICE" ]; then
    echo "Error: Could not find keyboard device."
    exit 1
fi

DEVICE="/dev/input/$DEVICE"
echo "Listening on: $DEVICE"

# Main loop using evtest
# value 1 = Press
# value 0 = Release
if command -v evtest &> /dev/null; then
    evtest "$DEVICE" | while read -r line; do
        if [[ "$line" == *"code 425"* ]]; then
            if [[ "$line" == *"value 1"* ]]; then
                # Press
                "$HANDLER_SCRIPT" press &
            elif [[ "$line" == *"value 0"* ]]; then
                # Release
                "$HANDLER_SCRIPT" release &
            fi
        fi
    done
else
    echo "Error: 'evtest' not found."
    exit 1
fi