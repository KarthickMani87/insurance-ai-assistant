import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load env vars from .env file
load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
BACKEND_TEAM_EMAIL = os.getenv("BACKEND_TEAM_EMAIL")

def send_email(subject: str, email_content: str):
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = BACKEND_TEAM_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(email_content, "plain"))   # ✅ fixed

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Secure connection
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        print(f"✅ Email sent to backend team: {BACKEND_TEAM_EMAIL}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")