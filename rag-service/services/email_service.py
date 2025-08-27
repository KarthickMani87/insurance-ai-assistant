import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
BACKEND_TEAM_EMAIL = os.getenv("BACKEND_TEAM_EMAIL")

def send_summary_email(conversation: list, conclusion: str, next_step: str):
    """Send conversation summary to backend team"""
    subject = "Insurance Assistant - Conversation Summary"
    body = f"""
    📝 Conversation Summary

    Conversation Highlights:
    {conversation}

    📌 Conclusion:
    {conclusion}

    🚀 Suggested Next Step:
    {next_step}
    """

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = BACKEND_TEAM_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    print(f"✅ Email sent to backend team: {BACKEND_TEAM_EMAIL}")

