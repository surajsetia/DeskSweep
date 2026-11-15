
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def get_database_url():
    url = os.getenv("DATABASE_URL", "").strip()

    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


@contextmanager
def get_db():
    conn = psycopg.connect(
        get_database_url(),
        row_factory=dict_row,
        connect_timeout=15,
        prepare_threshold=None
    )

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def init_db():
    statements = [
        """
        CREATE TABLE IF NOT EXISTS customers (
            client_id TEXT PRIMARY KEY,
            attempts_used INTEGER NOT NULL DEFAULT 0
                CHECK (attempts_used >= 0),
            is_pro BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL REFERENCES customers(client_id),
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'created',
            created_at TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(order_id),
            client_id TEXT NOT NULL REFERENCES customers(client_id),
            created_at TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS webhook_events (
            event_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_orders_client
        ON orders(client_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_payments_order
        ON payments(order_id)
        """
    ]

    with get_db() as conn:
        for statement in statements:
            conn.execute(statement)
