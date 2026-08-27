"""
Storage for found items.

SQLite by default, which needs no setup and keeps local development simple.
Set DATABASE_URL to a postgres:// URL and it uses Postgres instead -- which is
what production needs, because Render's free instances have no persistent disk
for a SQLite file to live on.

The two dialects differ in three small ways, all handled here: the parameter
placeholder (? vs %s), how a new row's id comes back (lastrowid vs RETURNING),
and how to list existing columns when migrating.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
DB_PATH = os.environ.get("LNF_DB", os.path.join(os.path.dirname(__file__), "lostfound.db"))

SERIAL = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS items (
    id             {SERIAL},
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

# Columns added after the first release; existing databases get them on boot.
ADDED_COLUMNS = {
    "posted_by": "TEXT",
    "posted_by_name": "TEXT",
    "claimed_by": "TEXT",
    "claimed_at": "TEXT",
}


def backend_name():
    if not IS_POSTGRES:
        return f"SQLite ({os.path.basename(DB_PATH)})"
    host = urlparse(DATABASE_URL).hostname or "?"
    return f"Postgres ({host})"


def _q(sql):
    """SQLite takes ?, Postgres takes %s. Queries are written with ?."""
    return sql.replace("?", "%s") if IS_POSTGRES else sql


class _Conn:
    """Thin wrapper so both drivers behave the same at the call sites."""

    def __init__(self):
        if IS_POSTGRES:
            import psycopg
            from psycopg.rows import dict_row

            self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            self.raw = sqlite3.connect(DB_PATH)
            self.raw.row_factory = sqlite3.Row

    def execute(self, sql, args=()):
        cur = self.raw.cursor()
        cur.execute(_q(sql), args)
        return cur

    def executescript(self, script):
        if IS_POSTGRES:
            cur = self.raw.cursor()
            for stmt in filter(None, (s.strip() for s in script.split(";"))):
                cur.execute(stmt)
        else:
            self.raw.executescript(script)

    def columns(self, table):
        if IS_POSTGRES:
            cur = self.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (table,),
            )
            return {r["column_name"] for r in cur.fetchall()}
        return {r["name"] for r in self.execute(f"PRAGMA table_info({table})").fetchall()}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        self.raw.close()
        return False


def connect():
    return _Conn()


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)
        have = conn.columns("items")
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
    sql = f"INSERT INTO items ({cols}) VALUES ({marks})"

    with connect() as conn:
        if IS_POSTGRES:
            cur = conn.execute(sql + " RETURNING id", list(fields.values()))
            return cur.fetchone()["id"]
        return conn.execute(sql, list(fields.values())).lastrowid


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
    """Remove the row and return it, so the caller can clean up the photos."""
    item = get_item(item_id)
    if item:
        with connect() as conn:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return item


def counts():
    # CASE WHEN rather than SQLite's `SUM(status = 'x')`, which Postgres rejects.
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "  SUM(CASE WHEN status = 'unclaimed' THEN 1 ELSE 0 END) AS unclaimed, "
            "  SUM(CASE WHEN status = 'claimed' THEN 1 ELSE 0 END) AS claimed "
            "FROM items"
        ).fetchone()
    return {k: (row[k] or 0) for k in ("total", "unclaimed", "claimed")}
