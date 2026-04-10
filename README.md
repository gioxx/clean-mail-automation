# Email Cleaner Docker Container

A Docker container to automatically clean an IMAP email inbox by deleting all emails older than a configurable number of days (default: 10). The cleanup runs periodically according to environment variables.

---

## Features

- Connects to any IMAP email server with specified credentials
- Supports one or multiple mailbox cleanups in the same container run
- Deletes emails older than N days (default: 10, configurable by env var or CLI)
- Optional Telegram notification after each cleanup run (success/failure, deleted count, duration)
- Web status page always available inside the container, showing configuration and last-run results
- Detailed logging with INFO and ERROR levels
- Executes cleanup immediately on the first container start
- Periodic scheduling using cron inside the container
- Logs available on container stdout, easy to monitor via Portainer or Docker CLI

---

## Prerequisites

### Running with Docker (recommended)

- Docker installed on your system
- IMAP email account with credentials ready
- Basic understanding of Docker image build and container run

### Running the script directly (without Docker)

`clean_email.py` has **no external dependencies** — it uses Python stdlib only. You can run it on any system with Python 3.8+:

```bash
# Set required environment variables
export IMAP_SERVER="imap.server.com"
export EMAIL_USER="your_username"
export EMAIL_PASS="your_password"

# Optional variables
export EMAIL_ADDRESS="mailbox@example.com"
export CLEAN_DAYS=10
export SEND_TELEGRAM_NOTIFICATIONS=true
export TELEGRAM_BOT_TOKEN="123456:ABCDEF"
export TELEGRAM_CHAT_ID="987654321"

# Run
python3 clean_email.py

# Or override retention days inline
python3 clean_email.py --days 30
```

When running directly, scheduling is handled externally (e.g. your system cron). The web status page (`status_server.py`) is **not** started automatically — it is only launched by `entrypoint.sh` inside the Docker container.

---

## Getting Started

### Official Prebuilt Images

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
  -e TELEGRAM_CHAT_ID="987654321" \
  -e SCHEDULE_DAY=1 \
  -e SCHEDULE_HOUR=1 \
  -e SCHEDULE_MIN=30 \
  -p 8080:8080 \
  --name email_cleaner ghcr.io/gioxx/clean-mail-automation:latest
```

If you prefer Docker Hub:

```bash
docker run -d -p 8080:8080 --name email_cleaner gfsolone/clean-mail-automation:latest
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
  -e TELEGRAM_CHAT_ID="987654321" \
  -e SCHEDULE_DAY=1 \
  -e SCHEDULE_HOUR=1 \
  -e SCHEDULE_MIN=30 \
  -p 8080:8080 \
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
| `MAILBOX` | script | No | `INBOX` | IMAP folder to clean. |
| `CLEAN_DAYS` | script | No | `10` | Deletes messages older than this many days. Ignored if `--days` is passed. |
| `MAILBOX_CONFIGS` | script | No | none | JSON array for multi-mailbox mode. If set, single-mailbox env vars become fallback/defaults. |
| `SEND_TELEGRAM_NOTIFICATIONS` | script | No | `false` | Enables Telegram notifications. True values: `1`, `true`, `yes`, `on` (case-insensitive). |
| `TELEGRAM_BOT_TOKEN` | script | Cond. | none | Required only when Telegram notifications are enabled. |
| `CLEAN_EMAIL_TELEGRAM_CHAT_ID` | script | Cond. | none | Dedicated chat id for this app. Takes priority over `TELEGRAM_CHAT_ID`. |
| `TELEGRAM_CHAT_ID` | script | Cond. | none | Fallback chat id if `CLEAN_EMAIL_TELEGRAM_CHAT_ID` is not set. |
| `TELEGRAM_TIMEOUT` | script | No | `10` | Timeout in seconds for Telegram API calls. |
| `TELEGRAM_NOTIFY_MODE` | script | No | `always` | `always`: notify after every run. `digest`: accumulate results and send on a separate schedule (see Digest). |
| `TELEGRAM_NOTIFY_ONLY_IF_DELETED` | script | No | `false` | When `true`, skip notifications for runs where no emails were deleted. Works with both modes. |
| `SCHEDULE_MIN` | container entrypoint | No | `0` | Cron minute (`0-59`). |
| `SCHEDULE_HOUR` | container entrypoint | No | `0` | Cron hour (`0-23`). |
| `SCHEDULE_DAY` | container entrypoint | No | `0` | Cron weekday (`0-7`, where `0`/`7` = Sunday). Use `*` to run every day. |
| `DIGEST_SCHEDULE_MIN` | container entrypoint | No | `0` | Digest send cron minute. Only used when `TELEGRAM_NOTIFY_MODE=digest`. |
| `DIGEST_SCHEDULE_HOUR` | container entrypoint | No | `8` | Digest send cron hour. Only used when `TELEGRAM_NOTIFY_MODE=digest`. |
| `DIGEST_SCHEDULE_DAY` | container entrypoint | No | `0` | Digest send cron weekday (same format as `SCHEDULE_DAY`). Only used when `TELEGRAM_NOTIFY_MODE=digest`. |
| `WEB_PORT` | container entrypoint | No | `8080` | Port the web status page listens on inside the container. Always started; override only if port `8080` conflicts. |

`SCHEDULE_DAY=1`, `SCHEDULE_HOUR=1`, `SCHEDULE_MIN=30` means: every Monday at 01:30.

---

### CLI Arguments (`clean_email.py`)

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `--days <int>` | No | `CLEAN_DAYS` or `10` | Override retention days for that run. If set, it has priority over `CLEAN_DAYS`. |
| `--send-digest` | No | — | Send the accumulated digest notification and clear the digest file, then exit. Called automatically by the digest cron inside the container. |

### Scheduling Environment Variables

Use these three variables together to define the cron schedule used by the container:

- `SCHEDULE_DAY`: Day of the week for the cron job (`0` or `7` = Sunday, `1` = Monday, ..., `6` = Saturday). Use `*` to run every day.
- `SCHEDULE_HOUR`: Hour of the day in 24h format (`0-23`)
- `SCHEDULE_MIN`: Minute of the hour (`0-59`)

Example:

- `SCHEDULE_DAY=1`
- `SCHEDULE_HOUR=1`
- `SCHEDULE_MIN=30`

This runs the cleanup every Monday at 01:30.

---

## Multi-Mailbox Mode

Set `MAILBOX_CONFIGS` as a JSON array to process multiple mailboxes in a single run.  
Each object can include:

- `imap_server`
- `imap_port` (optional, default `993`)
- `email_user`
- `email_pass`
- `email_address` (optional, defaults to `email_user`)
- `mailbox` (optional, default `INBOX`)
- `clean_days` (optional, default from `CLEAN_DAYS` or `10`)

Example:

```bash
-e MAILBOX_CONFIGS='[
  {"imap_server":"imap.server.com","email_user":"user1","email_pass":"pass1","email_address":"mail1@example.com","mailbox":"INBOX","clean_days":10},
  {"imap_server":"imap.server.com","email_user":"user2","email_pass":"pass2","email_address":"mail2@example.com","mailbox":"Archive","clean_days":30}
]'
```

---

## Web Status Page

The container always serves a read-only web status dashboard at `http://<host>:<port>/` (default port `8080`). The page shows:

- Configured mailboxes (IMAP server, folder, retention — passwords never exposed)
- Schedule (cron expression and human-readable description)
- Telegram notification status
- Results of the last cleanup run (per-mailbox status, deleted count, duration, errors)

The page auto-refreshes every 60 seconds.

The status page is only started by `entrypoint.sh` inside the Docker container. Running `clean_email.py` directly (outside Docker) does not start any web server.

### docker-compose example

> Ready-to-use compose files are available in the [`examples/`](examples/) folder:
> - [`docker-compose.single.yml`](examples/docker-compose.single.yml) — single mailbox with Telegram notifications
> - [`docker-compose.multi.yml`](examples/docker-compose.multi.yml) — multi-mailbox with weekly digest notifications

```yaml
services:
  email-cleaner:
    image: ghcr.io/gioxx/clean-mail-automation:latest
    environment:
      - IMAP_SERVER=imap.server.com
      - EMAIL_USER=your_username
      - EMAIL_PASS=your_password
      - CLEAN_DAYS=10
      - SCHEDULE_DAY=1
      - SCHEDULE_HOUR=1
      - SCHEDULE_MIN=30
    ports:
      - "8080:8080"
    restart: unless-stopped
```

To expose the status page on a different host port (e.g. `3200`), adjust the `ports` mapping accordingly — no need to set `WEB_PORT` unless you also want to change the internal port:

```yaml
ports:
  - "3200:8080"
```

### docker-compose example — multi-mailbox

Use `MAILBOX_CONFIGS` as a JSON array to clean multiple mailboxes in a single container. Each entry can target a different server, folder, and retention period:

```yaml
services:
  email-cleaner:
    image: ghcr.io/gioxx/clean-mail-automation:latest
    environment:
      - MAILBOX_CONFIGS=[
          {"imap_server":"imap.server.com","email_user":"user1@example.com","email_pass":"pass1","email_address":"user1@example.com","mailbox":"INBOX","clean_days":10},
          {"imap_server":"imap.server.com","email_user":"user2@example.com","email_pass":"pass2","email_address":"user2@example.com","mailbox":"INBOX","clean_days":30},
          {"imap_server":"imap.other.com","email_user":"user3@example.com","email_pass":"pass3","email_address":"user3@example.com","mailbox":"Archive","clean_days":60}
        ]
      - SCHEDULE_DAY=1
      - SCHEDULE_HOUR=1
      - SCHEDULE_MIN=30
      - SEND_TELEGRAM_NOTIFICATIONS=true
      - TELEGRAM_BOT_TOKEN=123456:ABCDEF
      - TELEGRAM_CHAT_ID=987654321
    ports:
      - "8080:8080"
    restart: unless-stopped
```

> **Note:** Docker Compose requires the `MAILBOX_CONFIGS` value to be on a single line or use a block scalar. The multi-line format above is for readability — in a real `.env` file or compose, write it as a single line or use the `env_file` option with proper quoting.

If you prefer keeping credentials out of the compose file, use an `.env` file:

```bash
# .env
MAILBOX_CONFIGS=[{"imap_server":"imap.server.com","email_user":"user1@example.com","email_pass":"pass1","mailbox":"INBOX","clean_days":10},{"imap_server":"imap.server.com","email_user":"user2@example.com","email_pass":"pass2","mailbox":"INBOX","clean_days":30}]
```

```yaml
# docker-compose.yml
services:
  email-cleaner:
    image: ghcr.io/gioxx/clean-mail-automation:latest
    env_file: .env
    environment:
      - SCHEDULE_DAY=1
      - SCHEDULE_HOUR=1
      - SCHEDULE_MIN=30
    ports:
      - "8080:8080"
    restart: unless-stopped
```

---

## Telegram Notifications

- Notifications are disabled by default. Set `SEND_TELEGRAM_NOTIFICATIONS=true` to enable them.
- When enabled, the script requires `TELEGRAM_BOT_TOKEN` plus a chat id.
- Chat id precedence: `CLEAN_EMAIL_TELEGRAM_CHAT_ID` first, then `TELEGRAM_CHAT_ID` as fallback. Use one of the two — there is no need to set both.
- Success notifications include: mailbox address, folder, retention days, deleted email count, and total duration.
- Failure notifications include: mailbox address, folder, retention days, duration, and error details.
- In multi-mailbox mode, one notification is sent per mailbox after each individual cleanup.

### Notification modes

| `TELEGRAM_NOTIFY_MODE` | Behaviour |
| --- | --- |
| `always` (default) | A notification is sent immediately after each cleanup run. |
| `digest` | Results are accumulated locally and sent together on a configurable schedule (see `DIGEST_SCHEDULE_*`). Useful when cleanup runs frequently but you want a single weekly summary. |

Set `TELEGRAM_NOTIFY_ONLY_IF_DELETED=true` (works with either mode) to suppress notifications when no emails were deleted — eliminates noise on quiet mailboxes.

**Digest example** — cleanup runs daily, digest every Sunday at 08:00:

```yaml
- TELEGRAM_NOTIFY_MODE=digest
- DIGEST_SCHEDULE_DAY=0
- DIGEST_SCHEDULE_HOUR=8
- DIGEST_SCHEDULE_MIN=0
```

---

## Project Structure

```
clean_email.py       Core script: connects via IMAP and deletes old emails, with logging
status_server.py     HTTP server for the web status page (started by entrypoint.sh, not by the script directly)
entrypoint.sh        Container entrypoint: sets up cron, starts the status server, then runs the first cleanup
Dockerfile           Docker image definition
```

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
- Use `MAILBOX_CONFIGS` to clean multiple mailboxes in a single container run

---

## Contribution

Contributions, issues, and feature requests are welcome! Feel free to fork the repository and submit pull requests.

---

## License

This project is licensed under the MIT License.
