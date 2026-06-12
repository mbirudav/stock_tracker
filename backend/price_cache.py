"""
In-memory price cache for FinAlly.

A single shared dict: { ticker: { price, previous_price, timestamp, baseline_price } }
The background market-data task writes here; SSE endpoints and trade endpoints read from it.
"""
from __future__ import annotations

import random
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

# Shared price cache: ticker -> price entry
# Structure: { "AAPL": { "price": 192.34, "previous_price": 192.10, "timestamp": "...", "baseline_price": 185.0 } }
price_cache: Dict[str, Dict] = {}
_cache_lock = threading.Lock()


def get_price(ticker: str) -> Optional[Dict]:
    """Return the current price entry for a ticker, or None if not in cache."""
    with _cache_lock:
        return price_cache.get(ticker.upper())


def set_price(ticker: str, price: float, previous_price: float) -> None:
    """Update the price cache for a ticker."""
    ticker = ticker.upper()
    now = datetime.now(timezone.utc).isoformat()
    with _cache_lock:
        entry = price_cache.get(ticker, {})
        baseline = entry.get("baseline_price", price)
        price_cache[ticker] = {
            "price": round(price, 4),
            "previous_price": round(previous_price, 4),
            "timestamp": now,
            "baseline_price": baseline,
        }


def initialize_ticker(ticker: str, seed_price: Optional[float] = None) -> float:
    """
    Ensure a ticker is in the price cache with an initial price.
    If seed_price is not provided, assigns a random price between $50 and $500.
    Returns the initial price.
    """
    ticker = ticker.upper()
    with _cache_lock:
        if ticker not in price_cache:
            if seed_price is None:
                seed_price = round(random.uniform(50.0, 500.0), 2)
            now = datetime.now(timezone.utc).isoformat()
            price_cache[ticker] = {
                "price": seed_price,
                "previous_price": seed_price,
                "timestamp": now,
                "baseline_price": seed_price,
            }
            return seed_price
        return price_cache[ticker]["price"]


def get_all_prices() -> Dict[str, Dict]:
    """Return a snapshot of the entire price cache."""
    with _cache_lock:
        return dict(price_cache)


def get_tickers() -> list:
    """Return the list of all tickers currently in the cache."""
    with _cache_lock:
        return list(price_cache.keys())
