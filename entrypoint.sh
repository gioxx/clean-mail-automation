#!/bin/bash
set -e

: "${SCHEDULE_MIN:=0}"
: "${SCHEDULE_HOUR:=0}"
: "${SCHEDULE_DAY:=0}"

# Generate the cron job and run the script for the first time now
echo "$SCHEDULE_MIN $SCHEDULE_HOUR * * $SCHEDULE_DAY python3 /app/clean_email.py >> /proc/1/fd/1 2>&1" > /etc/crontabs/root
python3 /app/clean_email.py

# Start cron in foreground
crond -f
