#!/bin/bash
set -e

: "${SCHEDULE_MIN:=0}"
: "${SCHEDULE_HOUR:=0}"
: "${SCHEDULE_DAY:=0}"

echo "$SCHEDULE_MIN $SCHEDULE_HOUR * * $SCHEDULE_DAY /usr/local/bin/python3 /app/clean_email.py >> /proc/1/fd/1 2>&1" > /tmp/cronjob
crontab /tmp/cronjob
/usr/local/bin/python3 /app/clean_email.py
cron -f
