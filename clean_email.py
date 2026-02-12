import argparse
import datetime
import imaplib
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

IMAP_SERVER = os.getenv('IMAP_SERVER')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
MAILBOX = 'INBOX'

def delete_old_emails(days=10):
    logging.info(f"Start cleaning emails older than {days} days.")
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select(MAILBOX)
        typ, data = mail.search(None, f'BEFORE {cutoff_date}')
        if typ != 'OK':
            logging.error("Error searching for emails.")
            return
        ids = data[0].split()
        logging.info(f"You have {len(ids)} emails to delete ...")
        for num in ids:
            mail.store(num, '+FLAGS', '\\Deleted')
        mail.expunge()
        mail.logout()
        logging.info("Cleaning successfully completed.")
    except Exception as e:
        logging.error(f"Error during cleaning: {e}")


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
    delete_old_emails(days)
