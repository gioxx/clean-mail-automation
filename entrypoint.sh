#!/bin/bash
set -e

: "${SCHEDULE_MIN:=0}"
: "${SCHEDULE_HOUR:=0}"
: "${SCHEDULE_DAY:=0}"
: "${DIGEST_SCHEDULE_MIN:=0}"
: "${DIGEST_SCHEDULE_HOUR:=8}"
: "${DIGEST_SCHEDULE_DAY:=0}"

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
DIGEST_SCHEDULE_MIN=$(sanitize_cron_field "$DIGEST_SCHEDULE_MIN" "0")
DIGEST_SCHEDULE_HOUR=$(sanitize_cron_field "$DIGEST_SCHEDULE_HOUR" "8")
DIGEST_SCHEDULE_DAY=$(sanitize_cron_field "$DIGEST_SCHEDULE_DAY" "0")

# Dump container environment for cron jobs (cron does not inherit Docker env vars).
/usr/local/bin/python3 -c "
import os, shlex
for k, v in os.environ.items():
    print(f'export {k}={shlex.quote(v)}')
" > /tmp/container_env.sh

echo "$SCHEDULE_MIN $SCHEDULE_HOUR * * $SCHEDULE_DAY /bin/bash -c 'source /tmp/container_env.sh && /usr/local/bin/python3 /app/clean_email.py' >> /proc/1/fd/1 2>&1" > /tmp/cronjob

# Add digest sender cron only when digest mode is active.
if [ "${TELEGRAM_NOTIFY_MODE:-always}" = "digest" ]; then
    echo "$DIGEST_SCHEDULE_MIN $DIGEST_SCHEDULE_HOUR * * $DIGEST_SCHEDULE_DAY /bin/bash -c 'source /tmp/container_env.sh && /usr/local/bin/python3 /app/clean_email.py --send-digest' >> /proc/1/fd/1 2>&1" >> /tmp/cronjob
fi

crontab /tmp/cronjob

# Start the web status server (always active; defaults to port 8080).
: "${WEB_PORT:=8080}"
export WEB_PORT
/usr/local/bin/python3 /app/status_server.py >> /proc/1/fd/1 2>&1 &

/usr/local/bin/python3 /app/clean_email.py
cron -f
