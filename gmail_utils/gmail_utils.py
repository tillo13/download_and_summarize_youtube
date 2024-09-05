import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from google_secret_utils import get_secret_version
from os import environ, path
from dotenv import load_dotenv
import logging

# Define the project ID and the secret IDs for username and app password
PROJECT_ID = 'YOURPROJECTID'
GMAIL_USERNAME_SECRET_ID = 'KUMORI_GMAIL_USERNAME'
GMAIL_APP_PASSWORD_SECRET_ID = 'KUMORI_GMAIL_APP_PASSWORD'

# Load environment variables from .env file if it exists
# Load environment variables from .env file if it exists
def load_env_file():
    # Assuming the .env file is always in the root of the project directory
    base_dir = path.abspath(path.join(path.dirname(__file__), '..'))
    dotenv_path = path.join(base_dir, '.env')
    if path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        return True
    return False


# Load Gmail credentials
def get_gmail_credentials():
    try:
        if load_env_file():
            return {
                'user': environ.get('2024may_17_GMAIL_USER'),
                'password': environ.get('2024may_17_GMAIL_PASSWORD')
            }
        else:
            raise Exception('.env file not found or not loaded')
    except Exception as env_error:
        logging.warning(f"Failed to load Gmail credentials from .env file: {env_error}")
        logging.info("Attempting to load credentials from Google Cloud Secret Manager")
        return {
            'user': get_secret_version(PROJECT_ID, GMAIL_USERNAME_SECRET_ID),
            'password': get_secret_version(PROJECT_ID, GMAIL_APP_PASSWORD_SECRET_ID),
        }

# Retrieve the Gmail credentials
gmail_credentials = get_gmail_credentials()
GMAIL_USER = gmail_credentials['user']
GMAIL_PASSWORD = gmail_credentials['password']

# Function to send emails
def send_email(subject, body, to_emails, attachment_paths=None, is_html=False):
    # Setup email headers and recipients
    message = MIMEMultipart()
    message['From'] = 'Kumori.ai <{}>'.format(GMAIL_USER)
    message['To'] = ', '.join(to_emails)
    message['Subject'] = subject

    if is_html:
        message.attach(MIMEText(body, 'html'))
    else:
        message.attach(MIMEText(body, 'plain'))
    
    # Process attachments if any
    if attachment_paths:
        for attachment_path in attachment_paths:
            part = MIMEBase('application', 'octet-stream')
            with open(attachment_path, 'rb') as file:
                part.set_payload(file.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                'attachment',
                filename=path.basename(attachment_path)
            )
            message.attach(part)
        
    # Connect to Gmail SMTP server and send email
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.set_debuglevel(1)  # Enable debug output to console
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.send_message(message)
        print('Email sent successfully')

# Function to create a sample text file
def create_sample_text_file(filename, content):
    with open(filename, 'w') as file:
        file.write(content)
    print(f"Created file {filename} with content: {content}")

# Test the function
if __name__ == '__main__':
    # Create sample text file
    filename = 'sample.txt'
    content = 'hello_world'
    create_sample_text_file(filename, content)

    # Sample usage
    subject = 'Test Email with Attachment from Python'
    body = 'This email contains an attachment sent from the python email utility.'
    to_emails = ['email@andy.com']

    # Get the full path to the attachment
    attachment_path = path.join(path.getcwd(), filename)
    attachment_paths = [attachment_path]

    send_email(subject, body, to_emails, attachment_paths)