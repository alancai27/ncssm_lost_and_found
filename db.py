"""SQLite storage for found items."""

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("LNF_DB", os.path.join(os.path.dirname(__file__), "lostfound.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    image          TEXT NOT NULL,
    thumb          TEXT NOT NULL,
    campus         TEXT NOT NULL DEFAULT 'durham',
    title          TEXT NOT NULL,
    category       TEXT,
    color          TEXT,
    brand          TEXT,
    ai_description TEXT,
    user_note      TEXT,
    tags           TEXT NOT NULL DEFAULT '[]',
    search_text    TEXT NOT NULL DEFAULT '',
    found_location TEXT,
    found_at       TEXT,
    finder_name    TEXT,
    finder_contact TEXT,
    posted_by      TEXT,
    posted_by_name TEXT,
    claimed_by     TEXT,
    claimed_at     TEXT,
    status         TEXT NOT NULL DEFAULT 'unclaimed',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_campus ON items(campus);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Columns added after the first release; existing databases get them on boot.
ADDED_COLUMNS = {
    "posted_by": "TEXT",
    "posted_by_name": "TEXT",
    "claimed_by": "TEXT",
    "claimed_at": "TEXT",
}


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)
        have = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        for name, coltype in ADDED_COLUMNS.items():
            if name not in have:
                conn.execute(f"ALTER TABLE items ADD COLUMN {name} {coltype}")


def _row_to_item(row):
    item = dict(row)
    try:
        item["tags"] = json.loads(item.get("tags") or "[]")
    except (ValueError, TypeError):
        item["tags"] = []
    return item


def add_item(**kw):
    """Insert an item. Returns the new row id."""
    fields = {
        "image": kw["image"],
        "thumb": kw["thumb"],
        "campus": kw.get("campus") or "durham",
        "title": kw.get("title") or "Found item",
        "category": kw.get("category"),
        "color": kw.get("color"),
        "brand": kw.get("brand"),
        "ai_description": kw.get("ai_description"),
        "user_note": kw.get("user_note"),
        "tags": json.dumps(kw.get("tags") or []),
        "search_text": kw.get("search_text") or "",
        "found_location": kw.get("found_location"),
        "found_at": kw.get("found_at"),
        "finder_name": kw.get("finder_name"),
        "finder_contact": kw.get("finder_contact"),
        "posted_by": kw.get("posted_by"),
        "posted_by_name": kw.get("posted_by_name"),
        "status": "unclaimed",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO items ({cols}) VALUES ({marks})", list(fields.values()))
        return cur.lastrowid


def get_item(item_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def list_items(campus=None, status="unclaimed", limit=None):
    sql = "SELECT * FROM items WHERE 1=1"
    args = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if campus:
        sql += " AND campus = ?"
        args.append(campus)
    sql += " ORDER BY id DESC"
    if limit:
        sql += " LIMIT ?"
        args.append(limit)
    with connect() as conn:
        return [_row_to_item(r) for r in conn.execute(sql, args).fetchall()]


def set_status(item_id, status, by_email=None):
    """Mark an item claimed/unclaimed, recording who did it and when."""
    claimed_by = by_email if status == "claimed" else None
    claimed_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if status == "claimed" else None
    with connect() as conn:
        conn.execute(
            "UPDATE items SET status = ?, claimed_by = ?, claimed_at = ? WHERE id = ?",
            (status, claimed_by, claimed_at, item_id),
        )


def delete_item(item_id):
    """Remove the row and return it, so the caller can clean up the files."""
    item = get_item(item_id)
    if item:
        with connect() as conn:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return item


def counts():
    with connect() as conn:
        row = conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(status = 'unclaimed') AS unclaimed, "
            "  SUM(status = 'claimed') AS claimed "
            "FROM items"
        ).fetchone()
    return {k: (row[k] or 0) for k in ("total", "unclaimed", "claimed")}
