"""
CRUD functions for the FinAlly database.

All functions accept an optional db_path parameter; when omitted they use
whatever path was last passed to init_db() (or the DB_PATH env var).

All timestamps are UTC ISO 8601 strings.

Design notes:
- Synchronous sqlite3 — FastAPI callers should use run_in_executor for
  long-running operations, but for short DB calls the overhead is negligible.
- Position rows are DELETED (not zeroed) when quantity reaches 0.
- UUIDs are generated here so callers get the id back immediately.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from .database import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# User / Cash Balance
# ---------------------------------------------------------------------------

def get_cash_balance(user_id: str = "default", db_path: Optional[str] = None) -> float:
    """Return the current cash balance for the given user."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"User '{user_id}' not found")
        return float(row["cash_balance"])


def update_cash_balance(
    user_id: str,
    new_balance: float,
    db_path: Optional[str] = None,
) -> None:
    """Set the cash balance for the given user to new_balance."""
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (new_balance, user_id),
        )


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

def get_watchlist(user_id: str = "default", db_path: Optional[str] = None) -> list[str]:
    """Return a list of ticker symbols on the user's watchlist, ordered by added_at."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at ASC",
            (user_id,),
        ).fetchall()
        return [row["ticker"] for row in rows]


def add_to_watchlist(
    user_id: str,
    ticker: str,
    db_path: Optional[str] = None,
) -> None:
    """
    Add ticker to the user's watchlist.

    Silently no-ops if the ticker is already present (UNIQUE constraint).
    ticker is stored in upper-case.
    """
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (_new_id(), user_id, ticker.upper(), _now_utc()),
        )


def remove_from_watchlist(
    user_id: str,
    ticker: str,
    db_path: Optional[str] = None,
) -> None:
    """Remove ticker from the user's watchlist. No-op if not present."""
    with get_db(db_path) as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        )


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def get_positions(
    user_id: str = "default",
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Return all open positions for the user.

    Each dict has keys: ticker, quantity, avg_cost, updated_at.
    """
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ticker, quantity, avg_cost, updated_at
            FROM positions
            WHERE user_id = ?
            ORDER BY ticker ASC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def upsert_position(
    user_id: str,
    ticker: str,
    quantity: float,
    avg_cost: float,
    db_path: Optional[str] = None,
) -> None:
    """
    Insert or replace a position row for (user_id, ticker).

    If quantity <= 0, the position is deleted instead (keeps the table clean).
    """
    if quantity <= 0:
        delete_position(user_id, ticker, db_path)
        return

    with get_db(db_path) as conn:
        # Check if a row already exists so we can keep its id stable.
        existing = conn.execute(
            "SELECT id FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE positions
                SET quantity = ?, avg_cost = ?, updated_at = ?
                WHERE user_id = ? AND ticker = ?
                """,
                (quantity, avg_cost, _now_utc(), user_id, ticker.upper()),
            )
        else:
            conn.execute(
                """
                INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_new_id(), user_id, ticker.upper(), quantity, avg_cost, _now_utc()),
            )


def delete_position(
    user_id: str,
    ticker: str,
    db_path: Optional[str] = None,
) -> None:
    """Delete a position row entirely (called when the user sells all shares)."""
    with get_db(db_path) as conn:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        )


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def insert_trade(
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    db_path: Optional[str] = None,
) -> str:
    """
    Append a trade record to the trades log.

    Args:
        side: 'buy' or 'sell'

    Returns:
        The UUID string of the new trade record.
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got: {side!r}")

    trade_id = _new_id()
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trade_id, user_id, ticker.upper(), side, quantity, price, _now_utc()),
        )
    return trade_id


# ---------------------------------------------------------------------------
# Portfolio Snapshots
# ---------------------------------------------------------------------------

def insert_snapshot(
    user_id: str,
    total_value: float,
    db_path: Optional[str] = None,
) -> None:
    """Record a portfolio value snapshot (used by the background task and trade executor)."""
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (_new_id(), user_id, total_value, _now_utc()),
        )


def get_snapshots(
    user_id: str = "default",
    limit: int = 500,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Return the most recent `limit` portfolio snapshots for the user.

    Each dict has keys: total_value, recorded_at.
    Results are ordered oldest-first so they can be plotted directly as a time series.
    """
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT total_value, recorded_at
            FROM portfolio_snapshots
            WHERE user_id = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        # Reverse so the returned list is chronological (oldest first)
        return [dict(row) for row in reversed(rows)]


# ---------------------------------------------------------------------------
# Chat Messages
# ---------------------------------------------------------------------------

def insert_message(
    user_id: str,
    role: str,
    content: str,
    actions: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """
    Store a chat message in the database.

    Args:
        role:    'user' or 'assistant'
        content: The message text.
        actions: Optional JSON string describing executed trades/watchlist changes.

    Returns:
        The UUID string of the new message record.
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"role must be 'user' or 'assistant', got: {role!r}")

    message_id = _new_id()
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, user_id, role, content, actions, _now_utc()),
        )
    return message_id


def get_recent_messages(
    user_id: str = "default",
    limit: int = 20,
    db_path: Optional[str] = None,
) -> list[dict]:
    """
    Return the most recent `limit` chat messages for the user.

    Each dict has keys: id, role, content, actions, created_at.
    Results are ordered oldest-first (chronological order for LLM context).
    """
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, actions, created_at
            FROM chat_messages
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        # Reverse so the returned list is chronological (oldest first)
        return [dict(row) for row in reversed(rows)]
