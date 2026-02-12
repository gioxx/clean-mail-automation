import argparse
import datetime
import imaplib
import logging
import os
import time
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

IMAP_SERVER = os.getenv('IMAP_SERVER')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
MAILBOX = 'INBOX'

def delete_old_emails(days=10):
    start_time = time.monotonic()
    deleted_count = 0
    status = "success"
    error_message = None
    mail = None

    logging.info(f"Start cleaning emails older than {days} days.")
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select(MAILBOX)
        typ, data = mail.search(None, f'BEFORE {cutoff_date}')
        if typ != 'OK':
            logging.error("Error searching for emails.")
            status = "search_error"
            error_message = "Error searching for emails."
            return {
                "status": status,
                "days": days,
                "deleted_count": deleted_count,
                "duration_seconds": time.monotonic() - start_time,
                "error_message": error_message,
            }
        ids = data[0].split()
        logging.info(f"You have {len(ids)} emails to delete ...")
        for num in ids:
            mail.store(num, '+FLAGS', '\\Deleted')
        deleted_count = len(ids)
        mail.expunge()
        logging.info("Cleaning successfully completed.")
    except Exception as e:
        logging.error(f"Error during cleaning: {e}")
        status = "error"
        error_message = str(e)
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                logging.warning("Error while closing IMAP session.")

    return {
        "status": status,
        "days": days,
        "deleted_count": deleted_count,
        "duration_seconds": time.monotonic() - start_time,
        "error_message": error_message,
    }


def resolve_clean_days(cli_days=None):
    if cli_days is not None:
        if cli_days < 0:
            logging.warning("Invalid --days value '%s'. Falling back to 10.", cli_days)
            return 10
        return cli_days

    env_days = os.getenv("CLEAN_DAYS")
    if env_days is None:
        return 10

    try:
        value = int(env_days)
        if value < 0:
            raise ValueError
        return value
    except ValueError:
        logging.warning("Invalid CLEAN_DAYS value '%s'. Falling back to 10.", env_days)
        return 10


def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    try:
        timeout = int(os.getenv("TELEGRAM_TIMEOUT", "10"))
    except ValueError:
        logging.warning("Invalid TELEGRAM_TIMEOUT value. Falling back to 10 seconds.")
        timeout = 10

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

    logging.info("Telegram notification sent.")
    return True


def notify_cleanup_result(result):
    if result["status"] == "success":
        message = (
            "Email cleanup completed.\n"
            f"Retention: {result['days']} days\n"
            f"Deleted emails: {result['deleted_count']}\n"
            f"Duration: {result['duration_seconds']:.2f}s"
        )
    else:
        message = (
            "Email cleanup failed.\n"
            f"Retention: {result['days']} days\n"
            f"Duration: {result['duration_seconds']:.2f}s\n"
            f"Error: {result['error_message'] or 'Unknown error'}"
        )
    send_telegram_message(message)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete IMAP emails older than N days.")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Delete emails older than this number of days (default: 10, or CLEAN_DAYS env var).",
    )
    args = parser.parse_args()
    days = resolve_clean_days(args.days)
    result = delete_old_emails(days)
    notify_cleanup_result(result)
