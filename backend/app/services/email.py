import os
import smtplib
from email.message import EmailMessage

from app.database import get_db
from app.services.access import utc_now


def send_pro_email(recipient: str):
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"

    if not host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL must be configured.")

    message = EmailMessage()
    message["Subject"] = "DeskSweep Pro is ready"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "Thanks for purchasing DeskSweep Pro. Your account is now unlocked "
        "for unlimited organization."
    )

    with smtplib.SMTP(host, port, timeout=15) as server:
        if use_tls:
            server.starttls()
        if username:
            server.login(username, password)
        server.send_message(message)


def send_pro_email_once(client_id: str, recipient: str):
    with get_db() as conn:
        customer = conn.execute(
            """
            SELECT pro_email_sent_at
            FROM customers
            WHERE client_id = %s
            FOR UPDATE
            """,
            (client_id,),
        ).fetchone()

        if not customer:
            raise RuntimeError("Customer record was not found for Pro email.")

        if customer["pro_email_sent_at"]:
            return

        send_pro_email(recipient)

        conn.execute(
            """
            UPDATE customers
            SET pro_email_sent_at = %s
            WHERE client_id = %s
            """,
            (utc_now(), client_id),
        )
