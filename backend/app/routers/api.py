
import os
import hmac
import hashlib
import json
import logging
import razorpay

from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request

from app.database import get_db
from app.schemas import LoginPayload, PaymentVerifyPayload, SignupPayload

from app.services.access import (
    FREE_ATTEMPTS,
    PRICE_PAISE,
    access_status,
    ensure_customer,
    record_successful_attempt,
    utc_now,
)
from app.services.auth import (
    create_access_token,
    get_current_email,
    hash_password,
    verify_password,
)
from app.services.email import send_pro_email_once


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


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

@router.post("/auth/signup")
def signup(payload: SignupPayload):
    email = str(payload.email).strip().lower()
    token = create_access_token(email)
    now = utc_now()

    with get_db() as conn:
        customer = conn.execute(
            """
            INSERT INTO customers (
                client_id,
                email,
                password_hash,
                attempts_used,
                is_pro,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, 0, FALSE, %s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING *
            """,
            (str(uuid4()), email, hash_password(payload.password), now, now),
        ).fetchone()

    if not customer:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    return {
        "access_token": token,
        "token_type": "bearer",
        **access_status(customer),
    }


@router.post("/auth/login")
def login(payload: LoginPayload):
    email = str(payload.email).strip().lower()

    with get_db() as conn:
        customer = conn.execute(
            "SELECT * FROM customers WHERE email = %s",
            (email,),
        ).fetchone()

    if not customer or not customer["password_hash"] or not verify_password(
        payload.password, customer["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Email or password is incorrect."
        )

    return {
        "access_token": create_access_token(email),
        "token_type": "bearer",
        **access_status(customer),
    }


@router.get("/access")
def get_access(email: str = Depends(get_current_email)):
    return access_status(ensure_customer(email))


# --------------------------------------------------
# COMPLETE USAGE
# --------------------------------------------------

@router.post("/usage/complete")
def complete_usage(email: str = Depends(get_current_email)):
    return record_successful_attempt(email)


# --------------------------------------------------
# CREATE RAZORPAY ORDER
# --------------------------------------------------

@router.post("/payments/create-order")
def create_order(email: str = Depends(get_current_email)):
    client, key_id = razorpay_client()

    customer = ensure_customer(email)
    client_id = customer["client_id"]

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
            "receipt": f"ds_{hashlib.sha256(email.encode('utf-8')).hexdigest()[:20]}",
            "notes": {
                "email": email,
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
    email: str
):
    with get_db() as conn:

        order = conn.execute(
            """
            SELECT o.*
            FROM orders o
            JOIN customers c ON c.client_id = o.client_id
            WHERE o.order_id = %s
              AND c.email = %s
            FOR UPDATE OF o
            """,
            (order_id, email)
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
            WHERE email = %s
            """,
            (email,)
        ).fetchone()

    return access_status(row)


# --------------------------------------------------
# VERIFY PAYMENT
# --------------------------------------------------

@router.post("/payments/verify")
def verify_payment(
    payload: PaymentVerifyPayload,
    email: str = Depends(get_current_email),
):
    client, _ = razorpay_client()

    order_id = payload.razorpay_order_id
    payment_id = payload.razorpay_payment_id
    customer = ensure_customer(email)

    with get_db() as conn:
        order = conn.execute(
            """
            SELECT o.*
            FROM orders o
            JOIN customers c ON c.client_id = o.client_id
            WHERE o.order_id = %s
              AND c.email = %s
            """,
            (order_id, email)
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
        email
    )

    email_sent = True
    try:
        send_pro_email_once(customer["client_id"], email)
    except Exception:
        email_sent = False
        logger.exception("Could not send Pro confirmation email")

    return {
        **result,
        "email_sent": email_sent,
        "message": (
            "Payment verified. DeskSweep Pro unlocked."
            if email_sent
            else "Pro is unlocked, but the confirmation email could not be sent."
        )
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

    email = None

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
        customer = conn.execute(
            "SELECT email FROM customers WHERE client_id = %s",
            (client_id,)
        ).fetchone()

        if not customer or not customer["email"]:
            raise HTTPException(
                status_code=400,
                detail="This order is not linked to an email account."
            )

        email = customer["email"]

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

    try:
        send_pro_email_once(client_id, email)
    except Exception:
        logger.exception("Could not send Pro confirmation email")
        raise HTTPException(
            status_code=503,
            detail="Pro is unlocked, but the confirmation email could not be sent yet."
        )

    with get_db() as conn:
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
