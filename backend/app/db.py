import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).with_name("schema.sql")


def get_db() -> sqlite3.Connection:
    """One connection per request, closed automatically at the end of it."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create tables if missing. Safe to call on every start."""
    db = get_db()
    db.execute("PRAGMA journal_mode = WAL")  # readers don't block the writer
    db.executescript(SCHEMA.read_text())
    db.commit()
