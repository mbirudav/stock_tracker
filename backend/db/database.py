"""
Database initialization and connection management for FinAlly.

SQLite with WAL mode for concurrent read/write access.
Lazy initialization: tables are created and seeded on first access.

Usage:
    # Initialize once at startup (idempotent):
    init_db()                    # uses DB_PATH env var or default
    init_db("/path/to/db")       # explicit path (useful in tests)

    # Per-request connection:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users_profile").fetchone()
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional


_DEFAULT_DB_PATH = "db/finally.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Module-level DB path, set by init_db() so get_db() knows where to connect.
_db_path: str = _DEFAULT_DB_PATH


def get_db_path() -> str:
    """Return the active database file path."""
    return os.getenv("DB_PATH", _db_path)


def _ensure_db_dir(db_path: str) -> None:
    """Create the directory for the database file if it doesn't exist."""
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Apply schema.sql (CREATE TABLE IF NOT EXISTS — fully idempotent)."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def _seed_default_data(conn: sqlite3.Connection) -> None:
    """Insert default user and watchlist only if users_profile is empty."""
    row = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()
    if row[0] > 0:
        return  # Already seeded

    now_utc = datetime.now(timezone.utc).isoformat()

    # Create default user profile
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES ('default', 10000.0, ?)",
        (now_utc,),
    )

    # Seed default watchlist tickers
    default_tickers = [
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    ]
    for ticker in default_tickers:
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), ticker, now_utc),
        )

    conn.commit()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize the database: ensure directory exists, apply schema, seed data.

    Args:
        db_path: Path to the SQLite file. Defaults to DB_PATH env var or
                 'db/finally.db'. Pass an explicit path in tests.
    """
    global _db_path

    resolved = db_path or os.getenv("DB_PATH", _DEFAULT_DB_PATH)
    _db_path = resolved

    _ensure_db_dir(resolved)

    conn = sqlite3.connect(resolved)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _apply_schema(conn)
        _seed_default_data(conn)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_db(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that yields a SQLite connection.

    Sets row_factory=sqlite3.Row so columns are accessible by name.
    Enables WAL mode and foreign keys on every connection.
    Commits on clean exit, rolls back on exception.

    Args:
        db_path: Override the DB path (mostly for tests). Falls back to
                 get_db_path() (env var or last path passed to init_db).
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
