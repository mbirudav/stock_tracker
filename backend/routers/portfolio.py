"""
Portfolio API router.

GET  /api/portfolio         — current positions, cash, total value, P&L
POST /api/portfolio/trade   — execute a buy or sell market order
GET  /api/portfolio/history — portfolio value snapshots over time
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..db.database import get_db
from ..price_cache import get_price, initialize_ticker
from ..snapshot import record_snapshot_now

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str  # "buy" or "sell"

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        return v.upper().strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_portfolio(conn, user_id: str = "default") -> Dict[str, Any]:
    """Build the full portfolio response dict."""
    profile = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    ).fetchone()
    cash_balance = profile["cash_balance"] if profile else 10000.0

    position_rows = conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions WHERE user_id = ? AND quantity > 0",
        (user_id,),
    ).fetchall()

    positions = []
    total_position_value = 0.0

    for row in position_rows:
        ticker = row["ticker"]
        quantity = row["quantity"]
        avg_cost = row["avg_cost"]

        price_entry = get_price(ticker)
        current_price = price_entry["price"] if price_entry else avg_cost

        unrealized_pnl = (current_price - avg_cost) * quantity
        pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0.0
        position_value = current_price * quantity
        total_position_value += position_value

        positions.append({
            "ticker": ticker,
            "quantity": quantity,
            "avg_cost": round(avg_cost, 4),
            "current_price": round(current_price, 4),
            "market_value": round(position_value, 4),
            "unrealized_pnl": round(unrealized_pnl, 4),
            "pnl_pct": round(pnl_pct, 4),
        })

    total_value = cash_balance + total_position_value

    return {
        "cash_balance": round(cash_balance, 4),
        "positions": positions,
        "total_value": round(total_value, 4),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/portfolio")
async def get_portfolio():
    """Return current portfolio: cash, positions with live P&L, total value."""
    with get_db() as conn:
        return _get_portfolio(conn)


@router.post("/portfolio/trade")
async def execute_trade(request: TradeRequest):
    """
    Execute a market order (buy or sell).

    Buy: checks sufficient cash (quantity * current_price).
    Sell: checks sufficient shares owned.
    If ticker not in watchlist, auto-adds it with a random seed price.

    Returns: {success, trade, portfolio} on success
             {success, error} with HTTP 400 on validation failure
    """
    ticker = request.ticker
    quantity = request.quantity
    side = request.side

    # Ensure ticker has a price
    price_entry = get_price(ticker)
    if price_entry is None:
        # Auto-add to price cache with random seed price
        seed_price = initialize_ticker(ticker)
        logger.info("Auto-initialized price for %s at %.2f", ticker, seed_price)
        price_entry = get_price(ticker)

    current_price = price_entry["price"]
    trade_value = current_price * quantity

    with get_db() as conn:
        # Check if ticker is in watchlist; if not, auto-add it
        existing = conn.execute(
            "SELECT id FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
                (str(uuid.uuid4()), ticker, datetime.now(timezone.utc).isoformat()),
            )
            logger.info("Auto-added %s to watchlist", ticker)

        # Get current cash balance
        profile = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ).fetchone()
        cash_balance = profile["cash_balance"] if profile else 10000.0

        if side == "buy":
            if cash_balance < trade_value:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": f"Insufficient cash. Need ${trade_value:.2f}, have ${cash_balance:.2f}.",
                    },
                )

            # Update cash
            new_cash = cash_balance - trade_value
            conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = 'default'",
                (new_cash,),
            )

            # Upsert position (weighted average cost)
            existing_pos = conn.execute(
                "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
                (ticker,),
            ).fetchone()

            if existing_pos:
                old_qty = existing_pos["quantity"]
                old_avg = existing_pos["avg_cost"]
                new_qty = old_qty + quantity
                new_avg = (old_avg * old_qty + current_price * quantity) / new_qty
                conn.execute(
                    """
                    UPDATE positions
                    SET quantity = ?, avg_cost = ?, updated_at = ?
                    WHERE user_id = 'default' AND ticker = ?
                    """,
                    (new_qty, new_avg, datetime.now(timezone.utc).isoformat(), ticker),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                    VALUES (?, 'default', ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), ticker, quantity, current_price, datetime.now(timezone.utc).isoformat()),
                )

        elif side == "sell":
            existing_pos = conn.execute(
                "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
                (ticker,),
            ).fetchone()

            owned_qty = existing_pos["quantity"] if existing_pos else 0.0
            if owned_qty < quantity:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": f"Insufficient shares. Need {quantity}, have {owned_qty}.",
                    },
                )

            # Update cash
            new_cash = cash_balance + trade_value
            conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = 'default'",
                (new_cash,),
            )

            # Update or delete position
            new_qty = owned_qty - quantity
            if new_qty <= 0:
                conn.execute(
                    "DELETE FROM positions WHERE user_id = 'default' AND ticker = ?",
                    (ticker,),
                )
            else:
                conn.execute(
                    """
                    UPDATE positions
                    SET quantity = ?, updated_at = ?
                    WHERE user_id = 'default' AND ticker = ?
                    """,
                    (new_qty, datetime.now(timezone.utc).isoformat(), ticker),
                )

        # Record the trade
        trade_id = str(uuid.uuid4())
        executed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES (?, 'default', ?, ?, ?, ?, ?)
            """,
            (trade_id, ticker, side, quantity, current_price, executed_at),
        )

        trade_record = {
            "id": trade_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": round(current_price, 4),
            "executed_at": executed_at,
        }

        # Build updated portfolio for response
        portfolio = _get_portfolio(conn)

    # Record portfolio snapshot after trade (outside db context)
    try:
        await record_snapshot_now()
    except Exception as exc:
        logger.warning("Failed to record snapshot after trade: %s", exc)

    return {
        "success": True,
        "trade": trade_record,
        "portfolio": portfolio,
    }


@router.get("/portfolio/history")
async def get_portfolio_history():
    """Return portfolio value snapshots over time for the P&L chart."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT total_value, recorded_at
            FROM portfolio_snapshots
            WHERE user_id = 'default'
            ORDER BY recorded_at ASC
            """,
        ).fetchall()

    snapshots = [
        {"total_value": row["total_value"], "recorded_at": row["recorded_at"]}
        for row in rows
    ]
    return {"snapshots": snapshots}
