"""
Portfolio snapshot background task for FinAlly.

Records total portfolio value to the database every 30 seconds,
and provides record_snapshot_now() for immediate capture after trades.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from .db.database import get_db
from .price_cache import get_price

logger = logging.getLogger(__name__)


def _compute_total_value(conn, user_id: str = "default") -> float:
    """Compute total portfolio value: cash + sum(qty * current_price) for all positions."""
    profile = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    ).fetchone()
    cash = profile["cash_balance"] if profile else 0.0

    positions = conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? AND quantity > 0",
        (user_id,),
    ).fetchall()

    total_position_value = 0.0
    for pos in positions:
        ticker = pos["ticker"]
        quantity = pos["quantity"]
        avg_cost = pos["avg_cost"]
        price_entry = get_price(ticker)
        current_price = price_entry["price"] if price_entry else avg_cost
        total_position_value += current_price * quantity

    return round(cash + total_position_value, 4)


async def record_snapshot_now(user_id: str = "default") -> None:
    """Compute and store a portfolio snapshot immediately (called after trades)."""
    try:
        with get_db() as conn:
            total_value = _compute_total_value(conn, user_id)
            conn.execute(
                "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, total_value, datetime.now(timezone.utc).isoformat()),
            )
        logger.debug("Recorded snapshot: total_value=%.2f", total_value)
    except Exception as exc:
        logger.error("Failed to record snapshot: %s", exc)


async def snapshot_background_task() -> None:
    """
    Background task: record portfolio snapshot every 30 seconds.
    Runs forever until the task is cancelled.
    """
    logger.info("Portfolio snapshot background task started")
    while True:
        try:
            await asyncio.sleep(30)
            await record_snapshot_now()
        except asyncio.CancelledError:
            logger.info("Portfolio snapshot background task stopped")
            break
        except Exception as exc:
            logger.error("Snapshot task error: %s", exc)
            await asyncio.sleep(5)  # brief backoff on error
