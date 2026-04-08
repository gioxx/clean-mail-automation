import argparse
import datetime
import imaplib
import json
import logging
import os
import time
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEFAULT_MAILBOX = "INBOX"
STATE_FILE = "/tmp/clean_mail_last_run.json"

SEND_TELEGRAM_NOTIFICATIONS = os.getenv("SEND_TELEGRAM_NOTIFICATIONS", "false").strip().lower() in {
    "1", "true", "yes", "on"
}


def parse_non_negative_int(value, default_value, context_name):
    try:
        parsed_value = int(value)
        if parsed_value < 0:
            raise ValueError
        return parsed_value
    except (TypeError, ValueError):
        logging.warning("Invalid %s value '%s'. Falling back to %s.", context_name, value, default_value)
        return default_value


def resolve_clean_days(cli_days=None, configured_days=None):
    if cli_days is not None:
        if cli_days < 0:
            logging.warning("Invalid --days value '%s'. Falling back to 10.", cli_days)
            return 10
        return cli_days

    if configured_days is None:
        configured_days = os.getenv("CLEAN_DAYS")
    if configured_days is None:
        return 10

    return parse_non_negative_int(configured_days, 10, "CLEAN_DAYS")


def get_config_value(config, *keys, default=None):
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return value
    return default


def build_single_mailbox_config(cli_days):
    email_user = os.getenv("EMAIL_USER")
    return {
        "imap_server": os.getenv("IMAP_SERVER"),
        "imap_port": parse_non_negative_int(os.getenv("IMAP_PORT", "993"), 993, "IMAP_PORT"),
        "email_user": email_user,
        "email_pass": os.getenv("EMAIL_PASS"),
        "email_address": os.getenv("EMAIL_ADDRESS") or email_user,
        "mailbox": os.getenv("MAILBOX", DEFAULT_MAILBOX),
        "clean_days": resolve_clean_days(cli_days),
    }


def normalize_mailbox_config(raw_config, index, cli_days):
    email_user = get_config_value(raw_config, "email_user", "EMAIL_USER")
    clean_days_raw = get_config_value(raw_config, "clean_days", "CLEAN_DAYS")

    return {
        "imap_server": get_config_value(raw_config, "imap_server", "IMAP_SERVER"),
        "imap_port": parse_non_negative_int(
            get_config_value(raw_config, "imap_port", "IMAP_PORT", default=993),
            993,
            f"MAILBOX_CONFIGS[{index}].imap_port",
        ),
        "email_user": email_user,
        "email_pass": get_config_value(raw_config, "email_pass", "EMAIL_PASS"),
        "email_address": get_config_value(raw_config, "email_address", "EMAIL_ADDRESS", default=email_user),
        "mailbox": get_config_value(raw_config, "mailbox", "MAILBOX", default=DEFAULT_MAILBOX),
        "clean_days": resolve_clean_days(cli_days, clean_days_raw),
    }


def load_mailbox_configs(cli_days):
    raw_configs = os.getenv("MAILBOX_CONFIGS")
    if not raw_configs:
        return [build_single_mailbox_config(cli_days)]

    try:
        parsed_configs = json.loads(raw_configs)
    except json.JSONDecodeError as error:
        logging.error("Invalid MAILBOX_CONFIGS JSON: %s. Falling back to single mailbox mode.", error)
        return [build_single_mailbox_config(cli_days)]

    if not isinstance(parsed_configs, list) or not parsed_configs:
        logging.error("MAILBOX_CONFIGS must be a non-empty JSON array. Falling back to single mailbox mode.")
        return [build_single_mailbox_config(cli_days)]

    normalized_configs = []
    for index, raw_config in enumerate(parsed_configs):
        if not isinstance(raw_config, dict):
            logging.warning("Skipping MAILBOX_CONFIGS[%s]: entry must be an object.", index)
            continue
        normalized_configs.append(normalize_mailbox_config(raw_config, index, cli_days))

    if not normalized_configs:
        logging.error("MAILBOX_CONFIGS contains no valid entries. Falling back to single mailbox mode.")
        return [build_single_mailbox_config(cli_days)]

    return normalized_configs


def validate_mailbox_config(mailbox_config):
    missing_fields = []
    for key in ("imap_server", "email_user", "email_pass"):
        if not mailbox_config.get(key):
            missing_fields.append(key)
    if missing_fields:
        logging.error(
            "Skipping mailbox %s due to missing required fields: %s",
            mailbox_config.get("email_address") or "unknown",
            ", ".join(missing_fields),
        )
        return False
    return True


def delete_old_emails(mailbox_config):
    start_time = time.monotonic()
    deleted_count = 0
    status = "success"
    error_message = None
    mail = None

    imap_server = mailbox_config["imap_server"]
    imap_port = mailbox_config["imap_port"]
    email_user = mailbox_config["email_user"]
    email_pass = mailbox_config["email_pass"]
    email_address = mailbox_config["email_address"] or email_user or "unknown"
    mailbox_name = mailbox_config["mailbox"]
    clean_days = mailbox_config["clean_days"]

    logging.info(
        "Start cleaning mailbox %s (folder: %s, user: %s), emails older than %s days.",
        email_address,
        mailbox_name,
        email_user,
        clean_days,
    )
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=clean_days)).strftime("%d-%b-%Y")

    try:
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.login(email_user, email_pass)
        mail.select(mailbox_name)
        search_status, search_data = mail.search(None, f"BEFORE {cutoff_date}")
        if search_status != "OK":
            status = "search_error"
            error_message = "Error searching for emails."
            logging.error("%s (%s / %s).", error_message, email_address, mailbox_name)
            return {
                "status": status,
                "days": clean_days,
                "deleted_count": deleted_count,
                "duration_seconds": time.monotonic() - start_time,
                "error_message": error_message,
                "mailbox_address": email_address,
                "mailbox_name": mailbox_name,
            }

        ids = search_data[0].split()
        logging.info("Mailbox %s (%s): %s emails to delete.", email_address, mailbox_name, len(ids))
        for num in ids:
            mail.store(num, "+FLAGS", "\\Deleted")
        deleted_count = len(ids)
        mail.expunge()
        logging.info("Cleaning completed for mailbox %s (%s).", email_address, mailbox_name)
    except Exception as error:
        status = "error"
        error_message = str(error)
        logging.error("Error during cleaning for mailbox %s (%s): %s", email_address, mailbox_name, error)
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                logging.warning("Error while closing IMAP session for mailbox %s.", email_address)

    return {
        "status": status,
        "days": clean_days,
        "deleted_count": deleted_count,
        "duration_seconds": time.monotonic() - start_time,
        "error_message": error_message,
        "mailbox_address": email_address,
        "mailbox_name": mailbox_name,
    }


def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("CLEAN_EMAIL_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logging.info(
            "Telegram notification skipped: TELEGRAM_BOT_TOKEN and chat id are required "
            "(CLEAN_EMAIL_TELEGRAM_CHAT_ID has priority over TELEGRAM_CHAT_ID)."
        )
        return False

    timeout = parse_non_negative_int(os.getenv("TELEGRAM_TIMEOUT", "10"), 10, "TELEGRAM_TIMEOUT")

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(api_url, data=payload, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                logging.error("Telegram notification failed with HTTP status %s.", response.status)
                return False
    except Exception as error:
        logging.error("Telegram notification failed: %s", error)
        return False

    logging.info("Telegram notification sent to chat %s.", chat_id)
    return True


def notify_cleanup_result(result):
    if not SEND_TELEGRAM_NOTIFICATIONS:
        logging.info(
            "Telegram notification skipped: SEND_TELEGRAM_NOTIFICATIONS is disabled (default: false)."
        )
        return

    mailbox_address = result["mailbox_address"] or "unknown"
    mailbox_name = result["mailbox_name"] or DEFAULT_MAILBOX

    if result["status"] == "success":
        message = (
            "Email cleanup completed.\n"
            f"Mailbox: {mailbox_address}\n"
            f"Folder: {mailbox_name}\n"
            f"Retention: {result['days']} days\n"
            f"Deleted emails: {result['deleted_count']}\n"
            f"Duration: {result['duration_seconds']:.2f}s"
        )
    else:
        message = (
            "Email cleanup failed.\n"
            f"Mailbox: {mailbox_address}\n"
            f"Folder: {mailbox_name}\n"
            f"Retention: {result['days']} days\n"
            f"Duration: {result['duration_seconds']:.2f}s\n"
            f"Error: {result['error_message'] or 'Unknown error'}"
        )

    sent = send_telegram_message(message)
    if sent:
        logging.info("Post-cleanup Telegram notification delivered for mailbox %s.", mailbox_address)


def save_run_state(results):
    state = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": [
            {
                "mailbox_address": r.get("mailbox_address", ""),
                "mailbox_name": r.get("mailbox_name", DEFAULT_MAILBOX),
                "status": r.get("status", "unknown"),
                "deleted_count": r.get("deleted_count", 0),
                "days": r.get("days", 0),
                "duration_seconds": round(r.get("duration_seconds", 0), 3),
                "error_message": r.get("error_message"),
            }
            for r in results
        ],
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except OSError as error:
        logging.warning("Could not write run state to %s: %s", STATE_FILE, error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete IMAP emails older than N days.")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Delete emails older than this number of days (default: 10, or CLEAN_DAYS env var).",
    )
    args = parser.parse_args()

    mailbox_configs = load_mailbox_configs(args.days)
    logging.info("Loaded %s mailbox configuration(s).", len(mailbox_configs))

    results = []
    for index, mailbox_config in enumerate(mailbox_configs, start=1):
        logging.info("Processing mailbox %s/%s.", index, len(mailbox_configs))
        if not validate_mailbox_config(mailbox_config):
            continue
        result = delete_old_emails(mailbox_config)
        notify_cleanup_result(result)
        results.append(result)

    save_run_state(results)
