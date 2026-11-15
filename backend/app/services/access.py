
from datetime import datetime, timezone

from fastapi import HTTPException

from app.database import get_db


FREE_ATTEMPTS = 2
PRICE_PAISE = 9900


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def ensure_customer(email: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM customers
            WHERE email = %s
            """,
            (email,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")

    return row


def access_status(row):
    used = int(row["attempts_used"])
    pro = bool(row["is_pro"])

    remaining = 0 if pro else max(0, FREE_ATTEMPTS - used)

    return {
        "email": row["email"],
        "is_pro": pro,
        "attempts_used": used,
        "free_attempts": FREE_ATTEMPTS,
        "attempts_remaining": remaining,
        "payment_required": not pro and remaining == 0,
        "price_inr": 99
    }


def record_successful_attempt(email: str):
    now = utc_now()

    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE customers
            SET
                attempts_used = attempts_used + 1,
                updated_at = %s
            WHERE
                email = %s
                AND is_pro = FALSE
                AND attempts_used < %s
            """,
            (now, email, FREE_ATTEMPTS)
        )

        row = conn.execute(
            """
            SELECT *
            FROM customers
            WHERE email = %s
            """,
            (email,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Account not found.")

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
            WHERE email = %s
            """,
            (email,)
        ).fetchone()

    return access_status(updated)
