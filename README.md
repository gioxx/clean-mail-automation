# Email Cleaner Docker Container

A Docker container to automatically clean an IMAP email inbox by deleting all emails older than a configurable number of days (default: 10). The cleanup runs periodically according to environment variables.

---

## Features

- Connects to any IMAP email server with specified credentials
- Deletes emails older than N days (default: 10, configurable by env var or CLI)
- Optional Telegram notification after each cleanup run (success/failure, deleted count, duration)
- Detailed logging with INFO and ERROR levels
- Executes cleanup immediately on the first container start
- Weekly repeated scheduling using cron inside the container
- Logs available on container stdout, easy to monitor via Portainer or Docker CLI

---

## Prerequisites

- Docker installed on your system
- IMAP email account with credentials ready
- Basic understanding of Docker image build and container run

---

## Getting Started

## Official Prebuilt Images

You can run this project without building locally by using one of the official prebuilt images:

- GHCR: `ghcr.io/gioxx/clean-mail-automation:latest`
- Docker Hub: `gfsolone/clean-mail-automation:latest`

### Option A: Run Official Prebuilt Image (Recommended)

This example runs cleanup every Monday at 1:30 AM:

```bash
docker run -d \
-e IMAP_SERVER="imap.server.com" \
-e IMAP_PORT=993 \
-e EMAIL_USER="your_username" \
-e EMAIL_PASS="your_password" \
-e EMAIL_ADDRESS="mailbox@example.com" \
-e CLEAN_DAYS=10 \
-e SEND_TELEGRAM_NOTIFICATIONS=true \
-e TELEGRAM_BOT_TOKEN="123456:ABCDEF" \
-e CLEAN_EMAIL_TELEGRAM_CHAT_ID="987654321" \
-e TELEGRAM_CHAT_ID="123456789" \
-e SCHEDULE_DAY=1 \
-e SCHEDULE_HOUR=1 \
-e SCHEDULE_MIN=30 \
--name email_cleaner ghcr.io/gioxx/clean-mail-automation:latest
```

If you prefer Docker Hub:

```bash
docker run -d --name email_cleaner gfsolone/clean-mail-automation:latest
```

### Option B: Build the Docker Image Locally

Clone this repository and build the image with:

```bash
docker build -t email-cleaner .
```

Then run the local image:

```bash
docker run -d \
-e IMAP_SERVER="imap.server.com" \
-e IMAP_PORT=993 \
-e EMAIL_USER="your_username" \
-e EMAIL_PASS="your_password" \
-e EMAIL_ADDRESS="mailbox@example.com" \
-e CLEAN_DAYS=10 \
-e SEND_TELEGRAM_NOTIFICATIONS=true \
-e TELEGRAM_BOT_TOKEN="123456:ABCDEF" \
-e CLEAN_EMAIL_TELEGRAM_CHAT_ID="987654321" \
-e TELEGRAM_CHAT_ID="123456789" \
-e SCHEDULE_DAY=1 \
-e SCHEDULE_HOUR=1 \
-e SCHEDULE_MIN=30 \
--name email_cleaner email-cleaner
```

---

## All Parameters

### Environment Variables (Container + Script)

| Name | Used by | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `IMAP_SERVER` | script | Yes | none | IMAP server hostname or IP. |
| `IMAP_PORT` | script | No | `993` | IMAP SSL port. |
| `EMAIL_USER` | script | Yes | none | Username for IMAP login. |
| `EMAIL_PASS` | script | Yes | none | Password for IMAP login. |
| `EMAIL_ADDRESS` | script | No | `EMAIL_USER` | Mailbox label shown in logs/notifications. |
| `CLEAN_DAYS` | script | No | `10` | Deletes messages older than this many days. Ignored if `--days` is passed. |
| `SEND_TELEGRAM_NOTIFICATIONS` | script | No | `false` | Enables Telegram notifications. True values: `1`, `true`, `yes`, `on` (case-insensitive). |
| `TELEGRAM_BOT_TOKEN` | script | Cond. | none | Required only when Telegram notifications are enabled. |
| `CLEAN_EMAIL_TELEGRAM_CHAT_ID` | script | Cond. | none | Dedicated chat id for this app. Takes priority over `TELEGRAM_CHAT_ID`. |
| `TELEGRAM_CHAT_ID` | script | Cond. | none | Fallback chat id if `CLEAN_EMAIL_TELEGRAM_CHAT_ID` is not set. |
| `TELEGRAM_TIMEOUT` | script | No | `10` | Timeout in seconds for Telegram API calls. |
| `SCHEDULE_MIN` | container entrypoint | No | `0` | Cron minute (`0-59`). |
| `SCHEDULE_HOUR` | container entrypoint | No | `0` | Cron hour (`0-23`). |
| `SCHEDULE_DAY` | container entrypoint | No | `0` | Cron weekday (`0-7`, where `0`/`7` = Sunday). |

`SCHEDULE_DAY=1`, `SCHEDULE_HOUR=1`, `SCHEDULE_MIN=30` means: every Monday at 01:30.

---

### CLI Arguments (`clean_email.py`)

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `--days <int>` | No | `CLEAN_DAYS` or `10` | Override retention days for that run. If set, it has priority over `CLEAN_DAYS`. |

### Scheduling Environment Variables

Use these three variables together to define the cron schedule used by the container:

- `SCHEDULE_DAY`: Day of the week for the cron job (`0` or `7` = Sunday, `1` = Monday, ..., `6` = Saturday)
- `SCHEDULE_HOUR`: Hour of the day in 24h format (`0-23`)
- `SCHEDULE_MIN`: Minute of the hour (`0-59`)

Example:

- `SCHEDULE_DAY=1`
- `SCHEDULE_HOUR=1`
- `SCHEDULE_MIN=30`

This runs the cleanup every Monday at 01:30.

---

## Telegram Notifications

- Notifications are disabled by default. Set `SEND_TELEGRAM_NOTIFICATIONS=true` to enable them.
- When enabled, the script requires `TELEGRAM_BOT_TOKEN` plus a chat id.
- Chat id precedence: `CLEAN_EMAIL_TELEGRAM_CHAT_ID` first, then `TELEGRAM_CHAT_ID` as fallback.
- Success notifications include: retention days, deleted email count, and total duration.
- Failure notifications include: retention days, duration, and error details.

---

## Project Structure

- `clean_email.py`: Python script that connects via IMAP and deletes old emails, with logging
- `entrypoint.sh`: Bash script that sets up the cron job and starts the cron daemon
- `Dockerfile`: Docker image definition file

---

## Logging

All logs generated by the Python script and cron job are sent to container stdout/stderr and can be viewed with:

```bash
docker logs email_cleaner
```

Or monitored live via Portainer's container logs UI.

---

## Customization

- Set `CLEAN_DAYS` (or pass `--days`) to change the number of days for deletion
- Adjust scheduling by setting different `SCHEDULE_DAY`, `SCHEDULE_HOUR`, and `SCHEDULE_MIN` values
- Extend logging or add notification mechanisms as needed

---

## Contribution

Contributions, issues, and feature requests are welcome! Feel free to fork the repository and submit pull requests.

---

## License

This project is licensed under the MIT License.

