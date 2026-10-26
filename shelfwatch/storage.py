"""Small SQLite store for reviewable drafts; photos never enter the database."""
from contextlib import contextmanager
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def database_path():
    folder = Path(os.getenv("SHELFWATCH_STATE_DIR", Path(__file__).resolve().parents[1] / ".data"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "shelfwatch.sqlite3"


@contextmanager
def connect():
    connection = sqlite3.connect(database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, draft TEXT NOT NULL, created_at TEXT NOT NULL, approved_at TEXT)")
    connection.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL)")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def save_order(order_id, draft):
    now = datetime.now(UTC).isoformat()
    with connect() as db:
        db.execute("INSERT INTO orders VALUES (?, ?, ?, NULL)", (order_id, draft, now))
        db.execute("INSERT INTO audit(created_at,event,detail) VALUES (?,?,?)", (now, "draft_created", json.dumps({"order_id": order_id})))


def approve(order_id):
    now = datetime.now(UTC).isoformat()
    with connect() as db:
        changed = db.execute("UPDATE orders SET approved_at=? WHERE id=? AND approved_at IS NULL", (now, order_id))
        if changed.rowcount != 1:
            return None
        row = dict(db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())
        db.execute("INSERT INTO audit(created_at,event,detail) VALUES (?,?,?)", (now, "draft_approved", json.dumps({"order_id": order_id, "sent": False})))
    return {**row, "approved": True}


def recent_orders(limit=20):
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))]
