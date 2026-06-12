"""
Watchlist API router.

GET    /api/watchlist          — list watched tickers with current prices
POST   /api/watchlist          — add a ticker
DELETE /api/watchlist/{ticker} — remove a ticker
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..db.database import get_db
from ..price_cache import get_price, initialize_ticker

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AddTickerRequest(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not v or not v.replace(".", "").replace("-", "").isalnum():
            raise ValueError("Invalid ticker symbol")
        if len(v) > 10:
            raise ValueError("Ticker symbol too long")
        return v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/watchlist")
async def get_watchlist():
    """Return all watched tickers with their latest prices from the price cache."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = 'default' ORDER BY added_at ASC"
        ).fetchall()

    result = []
    for row in rows:
        ticker = row["ticker"]
        price_entry = get_price(ticker)
        result.append({
            "ticker": ticker,
            "added_at": row["added_at"],
            "price": price_entry["price"] if price_entry else None,
            "previous_price": price_entry["previous_price"] if price_entry else None,
            "timestamp": price_entry["timestamp"] if price_entry else None,
            "baseline_price": price_entry.get("baseline_price") if price_entry else None,
        })

    return {"tickers": result}


@router.post("/watchlist")
async def add_ticker(request: AddTickerRequest):
    """
    Add a ticker to the watchlist.

    If the ticker is not in the simulator's known universe, assigns a random
    seed price between $50 and $500 and initializes it in the price cache.
    """
    ticker = request.ticker

    # Ensure the ticker has a price entry
    price_entry = get_price(ticker)
    if price_entry is None:
        seed_price = initialize_ticker(ticker)
        logger.info("Initialized price for new ticker %s at %.2f", ticker, seed_price)

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        ).fetchone()

        if existing:
            return {"message": f"{ticker} is already in the watchlist", "ticker": ticker}

        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), ticker, datetime.now(timezone.utc).isoformat()),
        )

    price_entry = get_price(ticker)
    return {
        "message": f"{ticker} added to watchlist",
        "ticker": ticker,
        "price": price_entry["price"] if price_entry else None,
    }


@router.delete("/watchlist/{ticker}")
async def remove_ticker(ticker: str):
    """
    Remove a ticker from the watchlist.

    Note: positions for that ticker are not affected — they still show in portfolio.
    """
    ticker = ticker.upper().strip()

    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"{ticker} not found in watchlist")

    return {"message": f"{ticker} removed from watchlist", "ticker": ticker}
