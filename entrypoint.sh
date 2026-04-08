#!/bin/bash
set -e

: "${SCHEDULE_MIN:=0}"
: "${SCHEDULE_HOUR:=0}"
: "${SCHEDULE_DAY:=0}"

# Sanitize cron fields to prevent injection attacks.
# Only digits, *, /, , and - are valid cron field characters.
sanitize_cron_field() {
    local value="$1"
    local default="$2"
    if echo "$value" | grep -qE '^[0-9*/,\-]+$'; then
        echo "$value"
    else
        echo "Unsupported cron field value '$value', falling back to '$default'." >&2
        echo "$default"
    fi
}

SCHEDULE_MIN=$(sanitize_cron_field "$SCHEDULE_MIN" "0")
SCHEDULE_HOUR=$(sanitize_cron_field "$SCHEDULE_HOUR" "0")
SCHEDULE_DAY=$(sanitize_cron_field "$SCHEDULE_DAY" "0")

echo "$SCHEDULE_MIN $SCHEDULE_HOUR * * $SCHEDULE_DAY /usr/local/bin/python3 /app/clean_email.py >> /proc/1/fd/1 2>&1" > /tmp/cronjob
crontab /tmp/cronjob

# Start the optional web status server when WEB_PORT is set.
if [ -n "${WEB_PORT:-}" ]; then
    /usr/local/bin/python3 /app/status_server.py >> /proc/1/fd/1 2>&1 &
fi

/usr/local/bin/python3 /app/clean_email.py
cron -f
