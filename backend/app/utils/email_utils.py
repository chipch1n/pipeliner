import logging
import os
import aiosmtplib
from email.message import EmailMessage

logger = logging.getLogger("app.email")

FIXED_RECIPIENT = os.getenv("LOCKOUT_ALERT_EMAIL", "admin@example.com")
SMTP_CONFIG = {
    "hostname": os.getenv("SMTP_HOST", "smtp.example.com"),
    "port": int(os.getenv("SMTP_PORT", "587")),
    "username": os.getenv("SMTP_USER", ""),
    "password": os.getenv("SMTP_PASSWORD", ""),
    "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() == "true",
}

async def send_lockout_alert(username: str) -> None:
    if not SMTP_CONFIG["username"] or not SMTP_CONFIG["password"]:
        logger.warning("SMTP not configured, skipping lockout email about user: %s", username)
        return

    msg = EmailMessage()
    msg["From"] = SMTP_CONFIG["username"]
    msg["To"] = FIXED_RECIPIENT
    msg["Subject"] = f"User Lockout: {username}"
    msg.set_content(
        f"User '{username}' has been locked out for 10 minutes after 3 failed login attempts."
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_CONFIG["hostname"],
            port=SMTP_CONFIG["port"],
            username=SMTP_CONFIG["username"],
            password=SMTP_CONFIG["password"],
            use_tls=SMTP_CONFIG["use_tls"],
        )
    except Exception as exc:
        logger.exception("Failed to send lockout email about user: %s", username, exc_info=exc)
        return

    logger.info("Sent lockout email about user: %s", username)
