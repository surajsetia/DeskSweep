
import os
import hmac
import hashlib
import json
import razorpay

from uuid import UUID
from fastapi import APIRouter, HTTPException, Request

from app.database import get_db
from app.schemas import ClientPayload, PaymentVerifyPayload

from app.services.access import (
    FREE_ATTEMPTS,
    PRICE_PAISE,
    access_status,
    ensure_customer,
    record_successful_attempt,
    utc_now,
)


router = APIRouter(prefix="/api")


# --------------------------------------------------
# RAZORPAY CLIENT
# --------------------------------------------------

def razorpay_client():
    key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()

    if not key_id or not key_secret:
        raise HTTPException(
            status_code=503,
            detail="Razorpay is not configured."
        )

    return razorpay.Client(
        auth=(key_id, key_secret)
    ), key_id


# --------------------------------------------------
# HEALTH
# --------------------------------------------------

@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "DeskSweep"
    }


# --------------------------------------------------
# CUSTOMER ACCESS
# --------------------------------------------------

@router.get("/access/{client_id}")
def get_access(client_id: str):
    try:
        client_id = str(UUID(client_id))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid client ID"
        )

    customer = ensure_customer(client_id)

    return access_status(customer)


# --------------------------------------------------
# COMPLETE USAGE
# --------------------------------------------------

@router.post("/usage/complete")
def complete_usage(payload: ClientPayload):
    return record_successful_attempt(
        str(payload.client_id)
    )


# --------------------------------------------------
# CREATE RAZORPAY ORDER
# --------------------------------------------------

@router.post("/payments/create-order")
def create_order(payload: ClientPayload):
    client, key_id = razorpay_client()

    client_id = str(payload.client_id)
    customer = ensure_customer(client_id)

    if customer["is_pro"]:
        return {
            "already_pro": True,
            "is_pro": True
        }

    if int(customer["attempts_used"]) < FREE_ATTEMPTS:
        raise HTTPException(
            status_code=409,
            detail=(
                "Use your 2 free successful organization "
                "attempts before purchasing Pro."
            )
        )

    try:
        order = client.order.create({
            "amount": PRICE_PAISE,
            "currency": "INR",
            "receipt": f"ds_{client_id.replace('-', '')[:20]}",
            "notes": {
                "client_id": client_id,
                "product": "DeskSweep Pro"
            }
        })

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Razorpay could not create the order. Please retry."
        )

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                order_id,
                client_id,
                amount,
                status,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                order["id"],
                client_id,
                PRICE_PAISE,
                "created",
                utc_now()
            )
        )

    return {
        "key_id": key_id,
        "order_id": order["id"],
        "amount": PRICE_PAISE,
        "currency": "INR",
        "name": "DeskSweep",
        "description": "DeskSweep Pro — one-time payment"
    }


# --------------------------------------------------
# APPLY VERIFIED PAYMENT
# --------------------------------------------------

def apply_verified_payment(
    payment_id: str,
    order_id: str,
    client_id: str
):
    with get_db() as conn:

        order = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE order_id = %s
              AND client_id = %s
            FOR UPDATE
            """,
            (order_id, client_id)
        ).fetchone()

        if not order or int(order["amount"]) != PRICE_PAISE:
            raise HTTPException(
                status_code=400,
                detail="Order not found or amount mismatch."
            )

        conn.execute(
            """
            INSERT INTO payments (
                payment_id,
                order_id,
                client_id,
                created_at
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (payment_id) DO NOTHING
            """,
            (payment_id, order_id, client_id, utc_now())
        )

        existing = conn.execute(
            """
            SELECT *
            FROM payments
            WHERE payment_id = %s
            """,
            (payment_id,)
        ).fetchone()

        if (
            existing["order_id"] != order_id
            or existing["client_id"] != client_id
        ):
            raise HTTPException(
                status_code=409,
                detail="Payment already applied to another order."
            )

        conn.execute(
            """
            UPDATE orders
            SET status = 'paid'
            WHERE order_id = %s
            """,
            (order_id,)
        )

        conn.execute(
            """
            UPDATE customers
            SET is_pro = TRUE, updated_at = %s
            WHERE client_id = %s
            """,
            (utc_now(), client_id)
        )

        row = conn.execute(
            """
            SELECT *
            FROM customers
            WHERE client_id = %s
            """,
            (client_id,)
        ).fetchone()

    return access_status(row)


# --------------------------------------------------
# VERIFY PAYMENT
# --------------------------------------------------

@router.post("/payments/verify")
def verify_payment(payload: PaymentVerifyPayload):
    client, _ = razorpay_client()

    client_id = str(payload.client_id)
    order_id = payload.razorpay_order_id
    payment_id = payload.razorpay_payment_id

    with get_db() as conn:
        order = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE order_id = %s
              AND client_id = %s
            """,
            (order_id, client_id)
        ).fetchone()

    if not order or int(order["amount"]) != PRICE_PAISE:
        raise HTTPException(
            status_code=400,
            detail="Order not found or amount mismatch."
        )

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": payload.razorpay_signature
        })

        payment = client.payment.fetch(payment_id)

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Payment verification failed."
        )

    if payment.get("order_id") != order_id:
        raise HTTPException(
            status_code=400,
            detail="Payment does not belong to this order."
        )

    if int(payment.get("amount", 0)) != PRICE_PAISE:
        raise HTTPException(
            status_code=400,
            detail="Payment amount mismatch."
        )

    if payment.get("currency") != "INR":
        raise HTTPException(
            status_code=400,
            detail="Invalid payment currency."
        )

    if payment.get("status") != "captured":
        raise HTTPException(
            status_code=402,
            detail="Payment is not captured yet."
        )

    result = apply_verified_payment(
        payment_id,
        order_id,
        client_id
    )

    return {
        **result,
        "message": "Payment verified. DeskSweep Pro unlocked."
    }


# --------------------------------------------------
# RAZORPAY WEBHOOK
# --------------------------------------------------

@router.post("/payments/webhook")
async def razorpay_webhook(request: Request):
    webhook_secret = os.getenv(
        "RAZORPAY_WEBHOOK_SECRET", ""
    ).strip()

    if not webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook secret is not configured."
        )

    body = await request.body()

    signature = request.headers.get(
        "X-Razorpay-Signature", ""
    )

    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    if not signature or not hmac.compare_digest(
        expected_signature,
        signature
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook signature."
        )

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook payload."
        )

    event = data.get("event")

    if event != "payment.captured":
        return {
            "status": "ignored",
            "event": event
        }

    payment = (
        data.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    payment_id = payment.get("id")
    order_id = payment.get("order_id")

    if not payment_id or not order_id:
        raise HTTPException(
            status_code=400,
            detail="Payment or order ID missing."
        )

    try:
        amount = int(payment.get("amount", 0))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Invalid payment amount."
        )

    if (
        payment.get("status") != "captured"
        or payment.get("currency") != "INR"
        or amount != PRICE_PAISE
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid payment details."
        )

    event_id = (
        request.headers.get("X-Razorpay-Event-Id")
        or hashlib.sha256(body).hexdigest()
    )

    with get_db() as conn:

        existing_event = conn.execute(
            """
            SELECT event_id
            FROM webhook_events
            WHERE event_id = %s
            """,
            (event_id,)
        ).fetchone()

        if existing_event:
            return {"status": "already_processed"}

        order = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE order_id = %s
            FOR UPDATE
            """,
            (order_id,)
        ).fetchone()

        if not order or int(order["amount"]) != PRICE_PAISE:
            raise HTTPException(
                status_code=400,
                detail="Order not found or amount mismatch."
            )

        client_id = order["client_id"]

        conn.execute(
            """
            INSERT INTO payments (
                payment_id,
                order_id,
                client_id,
                created_at
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (payment_id) DO NOTHING
            """,
            (payment_id, order_id, client_id, utc_now())
        )

        existing_payment = conn.execute(
            """
            SELECT *
            FROM payments
            WHERE payment_id = %s
            """,
            (payment_id,)
        ).fetchone()

        if (
            existing_payment["order_id"] != order_id
            or existing_payment["client_id"] != client_id
        ):
            raise HTTPException(
                status_code=409,
                detail="Payment already applied to another order."
            )

        conn.execute(
            """
            UPDATE orders
            SET status = 'paid'
            WHERE order_id = %s
            """,
            (order_id,)
        )

        conn.execute(
            """
            UPDATE customers
            SET is_pro = TRUE, updated_at = %s
            WHERE client_id = %s
            """,
            (utc_now(), client_id)
        )

        conn.execute(
            """
            INSERT INTO webhook_events (
                event_id,
                created_at
            )
            VALUES (%s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """,
            (event_id, utc_now())
        )

    return {
        "status": "success",
        "message": "DeskSweep Pro unlocked"
    }
