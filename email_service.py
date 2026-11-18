"""
Voicely Production Email Service.
Handles transactional email delivery (OTPs, password resets, welcome messages).
"""
import os
import smtplib
import ssl
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

logger = logging.getLogger("email_service")

# SMTP Configuration defaults (reads from environment variables)
DEFAULT_SMTP_HOST = os.environ.get("SMTP_HOST", "mail.api-maruthi.pikachuhosting.online")
DEFAULT_SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
DEFAULT_SMTP_USER = os.environ.get("SMTP_USER", "contact@api-maruthi.pikachuhosting.online")
DEFAULT_SMTP_PASS = os.environ.get("SMTP_PASS", "")
DEFAULT_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Voicely AI")


def get_smtp_config() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", DEFAULT_SMTP_HOST).strip(),
        "port": int(os.environ.get("SMTP_PORT", str(DEFAULT_SMTP_PORT))),
        "user": os.environ.get("SMTP_USER", DEFAULT_SMTP_USER).strip(),
        "password": os.environ.get("SMTP_PASS", DEFAULT_SMTP_PASS).strip(),
        "from_email": os.environ.get("SMTP_FROM_EMAIL", os.environ.get("SMTP_USER", DEFAULT_SMTP_USER)).strip(),
        "from_name": os.environ.get("SMTP_FROM_NAME", DEFAULT_FROM_NAME).strip(),
    }


def send_email(to_email: str, subject: str, text_content: str, html_content: str | None = None) -> bool:
    """Send an email using SMTP SSL (port 465) or STARTTLS (port 587)."""
    cfg = get_smtp_config()
    to_email = to_email.strip().lower()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=cfg["from_email"].split("@")[-1])

    msg.attach(MIMEText(text_content, "plain"))
    if html_content:
        msg.attach(MIMEText(html_content, "html"))

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                server.starttls(context=context)
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], [to_email], msg.as_string())

        logger.info("Successfully sent email to %s with subject: %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc, exc_info=True)
        return False


def send_otp_email(to_email: str, otp_code: str, purpose: str = "Password Reset") -> bool:
    """Send a stylized transactional OTP email."""
    subject = f"{otp_code} is your {purpose} code — Voicely"

    text_content = f"""Hello,

Your verification code for {purpose} is:

    {otp_code}

This code is valid for 10 minutes. If you did not make this request, please ignore this email or update your password.

Best regards,
The Voicely Team
api-maruthi.pikachuhosting.online
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7fafc; margin: 0; padding: 24px; color: #2d3748; }}
    .container {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 16px; padding: 36px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
    .logo-badge {{ display: inline-block; background: #ebf8ff; color: #3182ce; font-size: 13px; font-weight: 700; letter-spacing: 0.5px; padding: 6px 14px; border-radius: 9999px; margin-bottom: 24px; text-transform: uppercase; }}
    h1 {{ font-size: 24px; font-weight: 800; color: #1a202c; margin: 0 0 12px; letter-spacing: -0.5px; }}
    p {{ font-size: 15px; line-height: 1.6; color: #4a5568; margin: 0 0 20px; }}
    .otp-wrapper {{ background: #f8fafc; border: 2px dashed #cbd5e0; border-radius: 12px; padding: 24px; text-align: center; margin: 28px 0; }}
    .otp-code {{ font-family: 'Courier New', Courier, monospace; font-size: 38px; font-weight: 800; letter-spacing: 8px; color: #2b6cb0; margin: 0; }}
    .otp-expiry {{ font-size: 13px; color: #718096; margin-top: 8px; }}
    .notice {{ background: #fffaf0; border-left: 4px solid #dd6b20; padding: 12px 16px; border-radius: 6px; font-size: 13px; color: #7b341e; margin: 24px 0 0; }}
    .footer {{ margin-top: 32px; padding-top: 20px; border-top: 1px solid #edf2f7; font-size: 12px; color: #a0aec0; text-align: center; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo-badge">VOICELY SECURITY</div>
    <h1>{purpose} Verification</h1>
    <p>We received a request for <strong>{purpose}</strong> on your Voicely AI account. Use the one-time code below to proceed:</p>
    
    <div class="otp-wrapper">
      <div class="otp-code">{otp_code}</div>
      <div class="otp-expiry">⏱️ Expires in 10 minutes &bull; Single-use only</div>
    </div>

    <p>Do not share this code with anyone. Voicely staff will never ask for your verification code.</p>

    <div class="notice">
      If you did not request this code, you can safely disregard this email. Your account remains secure.
    </div>

    <div class="footer">
      Sent securely by Voicely AI Platform &bull; api-maruthi.pikachuhosting.online
    </div>
  </div>
</body>
</html>
"""
    return send_email(to_email, subject, text_content, html_content)
