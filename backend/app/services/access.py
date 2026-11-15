
from datetime import datetime, timezone

from fastapi import HTTPException

from app.database import get_db


FREE_ATTEMPTS = 2
PRICE_PAISE = 9900


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_customer(client_id: str):
    now = utc_now()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO customers (
                client_id,
                attempts_used,
                is_pro,
                created_at,
                updated_at
            )
            VALUES (%s, 0, FALSE, %s, %s)
            ON CONFLICT (client_id) DO NOTHING
            """,
            (client_id, now, now)
        )

        row = conn.execute(
            """
            SELECT *
            FROM customers
            WHERE client_id = %s
            """,
            (client_id,)
        ).fetchone()

    return row


def access_status(row):
    used = int(row["attempts_used"])
    pro = bool(row["is_pro"])

    remaining = 0 if pro else max(0, FREE_ATTEMPTS - used)

    return {
        "client_id": row["client_id"],
        "is_pro": pro,
        "attempts_used": used,
        "free_attempts": FREE_ATTEMPTS,
        "attempts_remaining": remaining,
        "payment_required": not pro and remaining == 0,
        "price_inr": 99
    }


def record_successful_attempt(client_id: str):
    ensure_customer(client_id)

    now = utc_now()

    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE customers
            SET
                attempts_used = attempts_used + 1,
                updated_at = %s
            WHERE
                client_id = %s
                AND is_pro = FALSE
                AND attempts_used < %s
            """,
            (now, client_id, FREE_ATTEMPTS)
        )

        row = conn.execute(
            """
            SELECT *
            FROM customers
            WHERE client_id = %s
            """,
            (client_id,)
        ).fetchone()

        if row["is_pro"]:
            return access_status(row)

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=402,
                detail=(
                    "Free attempts used. "
                    "Pay ₹99 to unlock unlimited organization."
                )
            )

        updated = conn.execute(
            """
            SELECT *
            FROM customers
            WHERE client_id = %s
            """,
            (client_id,)
        ).fetchone()

    return access_status(updated)
