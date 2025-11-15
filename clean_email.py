import os
import imaplib
import datetime
import logging

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

if __name__ == "__main__":
    delete_old_emails(10)
