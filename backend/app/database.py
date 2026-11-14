
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager


DB_PATH = Path(
    os.getenv("DATABASE_PATH", "./desksweep.db")
).resolve()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db():

    conn = sqlite3.connect(
        DB_PATH,
        timeout=15
    )

    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA foreign_keys=ON")

        yield conn

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def init_db():

    with get_db() as conn:

        conn.execute("PRAGMA journal_mode=WAL")

        conn.executescript("""

        CREATE TABLE IF NOT EXISTS customers (
            client_id TEXT PRIMARY KEY,
            attempts_used INTEGER NOT NULL DEFAULT 0
                CHECK(attempts_used >= 0),
            is_pro INTEGER NOT NULL DEFAULT 0
                CHECK(is_pro IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'created',
            created_at TEXT NOT NULL,

            FOREIGN KEY(client_id)
                REFERENCES customers(client_id)
        );


        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            created_at TEXT NOT NULL,

            FOREIGN KEY(order_id)
                REFERENCES orders(order_id),

            FOREIGN KEY(client_id)
                REFERENCES customers(client_id)
        );


        CREATE TABLE IF NOT EXISTS webhook_events (
            event_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );


        CREATE INDEX IF NOT EXISTS idx_orders_client
        ON orders(client_id);


        CREATE INDEX IF NOT EXISTS idx_payments_order
        ON payments(order_id);

        """)
