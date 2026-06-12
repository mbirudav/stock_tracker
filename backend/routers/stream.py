"""
SSE price streaming router.

GET /api/stream/prices — Server-Sent Events endpoint.
On connect: sends a snapshot event for all watched tickers immediately.
Then loops: pushes updates for all watched tickers every ~500ms.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..db.database import get_db
from ..price_cache import get_all_prices

logger = logging.getLogger(__name__)

router = APIRouter()


async def _price_event_generator() -> AsyncIterator[dict]:
    """Async generator that yields SSE events with price data."""
    # On connect: send an immediate snapshot of all current prices
    prices = get_all_prices()
    if prices:
        snapshot_data = []
        for ticker, entry in prices.items():
            snapshot_data.append({
                "ticker": ticker,
                "price": entry["price"],
                "previous_price": entry["previous_price"],
                "timestamp": entry["timestamp"],
                "baseline_price": entry.get("baseline_price", entry["price"]),
            })
        yield {
            "event": "snapshot",
            "data": json.dumps(snapshot_data),
        }

    # Continuous streaming loop
    while True:
        await asyncio.sleep(0.5)
        try:
            # Get the current watchlist from DB to know which tickers to stream
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT ticker FROM watchlist WHERE user_id = 'default'"
                ).fetchall()
                watched = {row["ticker"] for row in rows}

            prices = get_all_prices()
            updates = []
            for ticker in watched:
                entry = prices.get(ticker)
                if entry:
                    updates.append({
                        "ticker": ticker,
                        "price": entry["price"],
                        "previous_price": entry["previous_price"],
                        "timestamp": entry["timestamp"],
                    })

            if updates:
                for update in updates:
                    yield {
                        "event": "price",
                        "data": json.dumps(update),
                    }
        except asyncio.CancelledError:
            logger.info("SSE client disconnected")
            break
        except Exception as exc:
            logger.error("SSE stream error: %s", exc)
            await asyncio.sleep(1.0)


@router.get("/stream/prices")
async def stream_prices():
    """
    SSE endpoint that streams live price updates for all watched tickers.

    Events:
    - 'snapshot': sent once on connect with all current prices
    - 'price': sent every ~500ms for each watched ticker
    """
    return EventSourceResponse(_price_event_generator())
