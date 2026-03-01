from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone

from config import settings
from models import Contact, Message

DB_PATH = settings.database_path


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL DEFAULT '',
                timezone TEXT NOT NULL DEFAULT 'UTC',
                event_time_utc TEXT NOT NULL,
                event_description TEXT NOT NULL DEFAULT '',
                rsvp_status TEXT NOT NULL DEFAULT 'needsAction',
                current_state TEXT NOT NULL DEFAULT 'NEW',
                attempt_number INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL REFERENCES contacts(id),
                direction TEXT NOT NULL,
                body TEXT NOT NULL,
                action TEXT,
                reason TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER REFERENCES contacts(id),
                vapi_call_id TEXT,
                customer_number TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'initiated',
                ended_reason TEXT,
                duration_seconds INTEGER,
                summary TEXT,
                transcript TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


def _row_to_contact(row: tuple) -> Contact:
    return Contact(*row)


def _row_to_message(row: tuple) -> Message:
    return Message(*row)


async def get_contact_by_phone(phone: str) -> Contact | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM contacts WHERE phone = ?", (phone,))
        row = await cursor.fetchone()
        return _row_to_contact(row) if row else None


async def insert_contact(
    name: str,
    phone: str,
    event_time_utc: str,
    email: str = "",
    tz: str = "UTC",
    event_description: str = "",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT OR IGNORE INTO contacts
               (name, phone, email, timezone, event_time_utc, event_description,
                rsvp_status, current_state, attempt_number, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'needsAction', 'NEW', 0, ?, ?)""",
            (name, phone, email, tz, event_time_utc, event_description, now, now),
        )
        await db.commit()
        return cursor.lastrowid


async def update_contact(contact_id: int, **kwargs):
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [contact_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE contacts SET {sets} WHERE id = ?", vals)
        await db.commit()


async def get_all_contacts() -> list[Contact]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM contacts")
        rows = await cursor.fetchall()
        return [_row_to_contact(r) for r in rows]


async def insert_message(
    contact_id: int,
    direction: str,
    body: str,
    action: str | None = None,
    reason: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO messages (contact_id, direction, body, action, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (contact_id, direction, body, action, reason, now),
        )
        await db.commit()
        return cursor.lastrowid


async def get_messages(contact_id: int) -> list[Message]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM messages WHERE contact_id = ? ORDER BY created_at ASC",
            (contact_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_message(r) for r in rows]


async def insert_call(
    customer_number: str,
    vapi_call_id: str | None = None,
    contact_id: int | None = None,
    status: str = "initiated",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO calls (contact_id, vapi_call_id, customer_number, status, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (contact_id, vapi_call_id, customer_number, status, now),
        )
        await db.commit()
        return cursor.lastrowid


async def update_call(vapi_call_id: str, **kwargs):
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [vapi_call_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE calls SET {sets} WHERE vapi_call_id = ?", vals)
        await db.commit()
