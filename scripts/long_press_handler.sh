#!/bin/bash

ACTION=$1
PID_FILE="/tmp/keypress.pid"
START_TIME_FILE="/tmp/keypress_start_time"
LONG_PRESS_DELAY=0.6 # 600ms

# Debug logging
exec >> /tmp/long_press_debug.log 2>&1
echo "--- $(date) --- ACTION: $ACTION"

if [ "$ACTION" == "press" ]; then
    date +%s.%N > $START_TIME_FILE
    echo "Press detected. Start time saved."
    (
        echo $$ > $PID_FILE
        sleep $LONG_PRESS_DELAY
        if [ -f $PID_FILE ] && [ "$(cat $PID_FILE)" == "$$" ]; then
            echo "Long press detected (timer expired). Activating NOS."
            echo '{"command":"activate_nos"}' | socat - /var/run/AcerSense.sock
        fi
    ) &
elif [ "$ACTION" == "release" ]; then
    if [ -f $PID_FILE ]; then
        SLEEP_PID=$(cat $PID_FILE)
        if ps -p $SLEEP_PID > /dev/null; then
            kill $SLEEP_PID
            echo "Timer killed."
        fi
        rm $PID_FILE
    fi
    if [ -f $START_TIME_FILE ]; then
        START_TIME=$(cat $START_TIME_FILE)
        END_TIME=$(date +%s.%N)
        rm $START_TIME_FILE
        IS_SHORT_PRESS=$(awk -v start="$START_TIME" -v end="$END_TIME" -v delay="$LONG_PRESS_DELAY" 'BEGIN { if ((end - start) < delay) { print 1 } else { print 0 } }')
        
        echo "Release detected. Duration: $(echo "$END_TIME - $START_TIME" | bc). Short Press: $IS_SHORT_PRESS"
        
        if [ "$IS_SHORT_PRESS" -eq 1 ]; then
            echo "Sending cycle_profile command..."
            echo '{"command":"cycle_profile"}' | socat - /var/run/AcerSense.sock
        else
            echo "Sending deactivate_nos command..."
            echo '{"command":"deactivate_nos"}' | socat - /var/run/AcerSense.sock
        fi
    else
        echo "Start time file not found on release!"
    fi
fi
