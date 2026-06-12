"""
Chat API router.

POST /api/chat — send a user message, get an AI response, auto-execute any
                 trades/watchlist changes the LLM requests.

Flow:
  1. Load portfolio context (cash, positions + P&L, watchlist with prices)
  2. Load last 20 chat messages from DB
  3. Build messages list for LLM (system + context + history + new user msg)
  4. Call LLM → structured JSON response
  5. Auto-execute trades from response.trades
  6. Auto-execute watchlist_changes from response.watchlist_changes
  7. Persist user message + assistant response + actions to DB
  8. Return {message, trades_executed, watchlist_changes_executed, errors}
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import crud
from ..db.database import get_db
from ..llm.client import call_llm
from ..price_cache import get_price, initialize_ticker

logger = logging.getLogger(__name__)

router = APIRouter()

USER_ID = "default"


# ---------------------------------------------------------------------------
# Pydantic request model
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_portfolio_context(conn) -> str:
    """
    Build a human-readable portfolio context string to inject into the LLM prompt.
    Returns a single string summarising cash, positions, and watchlist.
    """
    profile = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,)
    ).fetchone()
    cash = profile["cash_balance"] if profile else 10000.0

    position_rows = conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? AND quantity > 0",
        (USER_ID,),
    ).fetchall()

    positions_summary = []
    total_position_value = 0.0
    for row in position_rows:
        ticker = row["ticker"]
        quantity = row["quantity"]
        avg_cost = row["avg_cost"]
        price_entry = get_price(ticker)
        current_price = price_entry["price"] if price_entry else avg_cost
        market_value = current_price * quantity
        total_position_value += market_value
        unrealized_pnl = (current_price - avg_cost) * quantity
        positions_summary.append(
            f"{ticker}: {quantity:.2f} shares @ avg ${avg_cost:.2f}, "
            f"current ${current_price:.2f}, value ${market_value:.2f}, "
            f"P&L ${unrealized_pnl:+.2f}"
        )

    total_value = cash + total_position_value

    watchlist_rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at ASC",
        (USER_ID,),
    ).fetchall()
    watchlist_tickers = [row["ticker"] for row in watchlist_rows]
    watchlist_prices = []
    for ticker in watchlist_tickers:
        price_entry = get_price(ticker)
        price_str = f"${price_entry['price']:.2f}" if price_entry else "N/A"
        watchlist_prices.append(f"{ticker}@{price_str}")

    lines = [
        f"Cash: ${cash:.2f}",
        f"Total Portfolio Value: ${total_value:.2f}",
        f"Positions ({len(positions_summary)}): "
        + ("; ".join(positions_summary) if positions_summary else "none"),
        f"Watchlist: {', '.join(watchlist_prices) if watchlist_prices else 'empty'}",
    ]
    return "\n".join(lines)


def _execute_trade_internal(conn, ticker: str, side: str, quantity: float) -> dict[str, Any]:
    """
    Execute a single trade against the database.

    Returns a dict with keys: success (bool), trade (dict, on success),
    error (str, on failure).

    This mirrors the logic in routers/portfolio.py but works within an
    already-open connection and does NOT record a snapshot (caller handles that).
    """
    ticker = ticker.upper()

    # Ensure ticker has a price
    price_entry = get_price(ticker)
    if price_entry is None:
        seed_price = initialize_ticker(ticker)
        logger.info("Auto-initialized price for %s at %.2f", ticker, seed_price)
        price_entry = get_price(ticker)

    current_price = price_entry["price"]  # type: ignore[index]
    trade_value = current_price * quantity

    profile = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,)
    ).fetchone()
    cash_balance = profile["cash_balance"] if profile else 10000.0

    if side == "buy":
        if cash_balance < trade_value:
            return {
                "success": False,
                "ticker": ticker,
                "side": side,
                "quantity": quantity,
                "error": (
                    f"Insufficient cash. Need ${trade_value:.2f}, have ${cash_balance:.2f}."
                ),
            }

        new_cash = cash_balance - trade_value
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (new_cash, USER_ID),
        )

        existing = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (USER_ID, ticker),
        ).fetchone()

        if existing:
            old_qty = existing["quantity"]
            old_avg = existing["avg_cost"]
            new_qty = old_qty + quantity
            new_avg = (old_avg * old_qty + current_price * quantity) / new_qty
            conn.execute(
                "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? "
                "WHERE user_id = ? AND ticker = ?",
                (new_qty, new_avg, datetime.now(timezone.utc).isoformat(), USER_ID, ticker),
            )
        else:
            conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), USER_ID, ticker, quantity,
                    current_price, datetime.now(timezone.utc).isoformat(),
                ),
            )

        # Auto-add to watchlist so the ticker gets streamed prices
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), USER_ID, ticker, datetime.now(timezone.utc).isoformat()),
        )

    elif side == "sell":
        existing = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (USER_ID, ticker),
        ).fetchone()
        owned = existing["quantity"] if existing else 0.0

        if owned < quantity:
            return {
                "success": False,
                "ticker": ticker,
                "side": side,
                "quantity": quantity,
                "error": f"Insufficient shares. Need {quantity}, have {owned}.",
            }

        new_cash = cash_balance + trade_value
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (new_cash, USER_ID),
        )

        new_qty = owned - quantity
        if new_qty <= 0:
            conn.execute(
                "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
                (USER_ID, ticker),
            )
        else:
            conn.execute(
                "UPDATE positions SET quantity = ?, updated_at = ? "
                "WHERE user_id = ? AND ticker = ?",
                (new_qty, datetime.now(timezone.utc).isoformat(), USER_ID, ticker),
            )
    else:
        return {
            "success": False,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "error": f"Unknown trade side: {side!r}",
        }

    # Record the trade
    trade_id = str(uuid.uuid4())
    executed_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade_id, USER_ID, ticker, side, quantity, current_price, executed_at),
    )

    return {
        "success": True,
        "trade": {
            "id": trade_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": round(current_price, 4),
            "executed_at": executed_at,
        },
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Send a user message to FinAlly AI assistant.

    Returns the assistant's response plus a summary of any auto-executed
    trades and watchlist changes.
    """
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # 1. Build portfolio context + load chat history (single DB open)
    with get_db() as conn:
        portfolio_context = _build_portfolio_context(conn)
        recent_messages = conn.execute(
            """
            SELECT role, content FROM chat_messages
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (USER_ID,),
        ).fetchall()

    # 2. Assemble the messages list for the LLM
    #    history is reversed (DESC from DB → oldest-first for LLM)
    history = list(reversed(recent_messages))

    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You are FinAlly, an AI trading assistant for a simulated portfolio. "
                "Be concise and data-driven. Analyse positions, suggest trades, and "
                "execute them when the user asks or agrees. Manage the watchlist proactively. "
                "Always respond with valid JSON matching the schema: "
                "{\"message\": \"<text>\", \"trades\": [{\"ticker\": \"...\", \"side\": \"buy|sell\", "
                "\"quantity\": <number>}], \"watchlist_changes\": [{\"ticker\": \"...\", "
                "\"action\": \"add|remove\"}]}. "
                "The trades and watchlist_changes arrays may be empty."
            ),
        },
        {
            "role": "system",
            "content": f"Current portfolio state:\n{portfolio_context}",
        },
    ]

    for row in history:
        messages.append({"role": row["role"], "content": row["content"]})

    messages.append({"role": "user", "content": user_message})

    # 3. Call LLM
    llm_result = call_llm(messages)

    # 4 & 5. Auto-execute trades and watchlist changes
    trades_executed: list[dict] = []
    watchlist_changes_executed: list[dict] = []
    errors: list[str] = []

    raw_trades = llm_result.get("trades") or []
    raw_wl_changes = llm_result.get("watchlist_changes") or []

    with get_db() as conn:
        # Execute trades
        for trade in raw_trades:
            ticker = str(trade.get("ticker", "")).upper().strip()
            side = str(trade.get("side", "")).lower()
            try:
                quantity = float(trade.get("quantity", 0))
            except (TypeError, ValueError):
                errors.append(f"Invalid quantity for trade: {trade}")
                continue

            if not ticker or side not in ("buy", "sell") or quantity <= 0:
                errors.append(f"Skipping invalid trade spec: {trade}")
                continue

            result = _execute_trade_internal(conn, ticker, side, quantity)
            if result["success"]:
                trades_executed.append(result["trade"])
            else:
                errors.append(result["error"])

        # Execute watchlist changes
        for change in raw_wl_changes:
            ticker = str(change.get("ticker", "")).upper().strip()
            action = str(change.get("action", "")).lower()

            if not ticker or action not in ("add", "remove"):
                errors.append(f"Skipping invalid watchlist change: {change}")
                continue

            try:
                if action == "add":
                    conn.execute(
                        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) "
                        "VALUES (?, ?, ?, ?)",
                        (str(uuid.uuid4()), USER_ID, ticker, datetime.now(timezone.utc).isoformat()),
                    )
                    # Ensure it has a price in cache
                    if get_price(ticker) is None:
                        initialize_ticker(ticker)
                    watchlist_changes_executed.append({"ticker": ticker, "action": "add"})
                elif action == "remove":
                    conn.execute(
                        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                        (USER_ID, ticker),
                    )
                    watchlist_changes_executed.append({"ticker": ticker, "action": "remove"})
            except Exception as exc:
                logger.exception("Watchlist change failed for %s %s: %s", action, ticker, exc)
                errors.append(f"Watchlist {action} {ticker} failed: {exc}")

        # 6. Persist user message
        user_msg_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, 'user', ?, NULL, ?)",
            (user_msg_id, USER_ID, user_message, datetime.now(timezone.utc).isoformat()),
        )

        # 7. Persist assistant response with actions JSON
        actions_json = json.dumps({
            "trades": trades_executed,
            "watchlist_changes": watchlist_changes_executed,
        }) if (trades_executed or watchlist_changes_executed) else None

        assistant_msg_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, 'assistant', ?, ?, ?)",
            (
                assistant_msg_id,
                USER_ID,
                llm_result.get("message", ""),
                actions_json,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    # 8. Return response
    return {
        "message": llm_result.get("message", ""),
        "trades_executed": trades_executed,
        "watchlist_changes_executed": watchlist_changes_executed,
        "errors": errors,
    }
