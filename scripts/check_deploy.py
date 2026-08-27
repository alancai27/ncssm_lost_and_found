#!/usr/bin/env python3
"""
Verify the production backends before deploying.

Run this with the same DATABASE_URL and S3_* values you are about to put in
Render, and it proves both actually work from your machine:

    DATABASE_URL='postgresql://...' \
    S3_BUCKET=... S3_ENDPOINT_URL=... S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... \
    python3 scripts/check_deploy.py

It writes a throwaway row and a throwaway object, reads both back, then
deletes them. Nothing is left behind.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

import db          # noqa: E402
import storage     # noqa: E402

FAIL = []


def step(label, fn):
    try:
        result = fn()
        print(f"  ok   {label}" + (f" — {result}" if result else ""))
        return True
    except Exception as exc:
        print(f"  FAIL {label}")
        print(f"         {type(exc).__name__}: {exc}")
        FAIL.append(label)
        return False


def main():
    print(f"\nDatabase: {db.backend_name()}")
    if not db.IS_POSTGRES:
        print("  NOTE: DATABASE_URL is not set, so this is checking SQLite, not")
        print("  the Postgres you are about to deploy against.")

    if step("connect and create schema", lambda: db.init() or "schema present"):
        item_id = None

        def insert():
            nonlocal item_id
            item_id = db.add_item(
                image="_preflight.jpg", thumb="_preflight_t.jpg",
                title="Preflight check", tags=["preflight"],
                search_text="preflight check",
            )
            return f"inserted id {item_id}"

        step("insert a row", insert)
        if item_id:
            step("read it back", lambda: repr(db.get_item(item_id)["title"]))
            step("list query", lambda: f"{len(db.list_items())} unclaimed")
            step("aggregate counts", lambda: db.counts())
            step("update status", lambda: db.set_status(item_id, "claimed", "preflight@example.edu") or "claimed")
            step("delete the row", lambda: db.delete_item(item_id) and "removed")

    print(f"\nPhoto storage: {storage.backend_name()}")
    for note in storage.config_warnings():
        print(f"  WARN {note}")
    if not storage.using_s3():
        print("  NOTE: S3_* not set, so this is checking the local filesystem.")
        print("  Render's free tier wipes that on every deploy.")

    payload = b"\xff\xd8\xff\xe0preflight"
    step("write an object", lambda: storage.save("_preflight.jpg", payload) or "written")
    step("read it back", lambda: "bytes match" if storage.load("_preflight.jpg")[0] == payload
         else (_ for _ in ()).throw(AssertionError("content differs")))
    step("delete it", lambda: storage.delete("_preflight.jpg") or "removed")

    print()
    if FAIL:
        print(f"{len(FAIL)} check(s) failed: {', '.join(FAIL)}")
        return 1
    print("All checks passed. Safe to deploy with these values.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
