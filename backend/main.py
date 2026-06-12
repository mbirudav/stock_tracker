"""
FinAlly Backend — FastAPI Application Entry Point

Single-port server that:
- Serves the Next.js static frontend from the /static directory
- Exposes all REST/SSE API endpoints under /api
- Starts background tasks on startup (market data, portfolio snapshots)
- Initializes the SQLite database on first run (schema + seed data)
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db.database import init_db
from .price_cache import initialize_ticker
from .snapshot import snapshot_background_task

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Market data background task
# ---------------------------------------------------------------------------

async def market_data_task() -> None:
    """
    Background task: polls the market data provider every 500ms and updates
    the in-memory price cache.

    Uses the simulator by default; switches to Massive (Polygon.io) if
    MASSIVE_API_KEY is set.
    """
    from .market_data_simulator import MarketDataSimulator
    from .price_cache import price_cache, set_price, initialize_ticker
    from .db.database import get_db

    massive_key = os.getenv("MASSIVE_API_KEY", "").strip()

    if massive_key:
        try:
            from .massive_api_interface import MassiveAPIProvider
            provider = MassiveAPIProvider(api_key=massive_key)
            logger.info("Using Massive (Polygon.io) market data provider")
        except Exception as exc:
            logger.warning("Failed to initialize Massive provider (%s), falling back to simulator", exc)
            provider = MarketDataSimulator()
            logger.info("Using market data simulator")
    else:
        provider = MarketDataSimulator()
        logger.info("Using market data simulator (no MASSIVE_API_KEY set)")

    # Prime the cache with initial prices for the default watchlist tickers
    default_tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
    for ticker in default_tickers:
        try:
            quote = provider.get_quote(ticker)
            from .price_cache import set_price
            set_price(ticker, quote.price, quote.prev_close or quote.price)
        except Exception as exc:
            logger.warning("Failed to prime price for %s: %s", ticker, exc)
            initialize_ticker(ticker)

    logger.info("Market data task started, polling every 500ms")

    while True:
        try:
            await asyncio.sleep(0.5)

            # Get current watchlist from DB
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT ticker FROM watchlist WHERE user_id = 'default'"
                ).fetchall()
                tickers = [row["ticker"] for row in rows]

            if not tickers:
                continue

            # Fetch quotes
            try:
                quotes = provider.get_quotes(tickers)
            except Exception as exc:
                logger.debug("Batch quote fetch failed (%s), skipping tick", exc)
                continue

            # Update price cache
            from .price_cache import price_cache as _cache, get_price, set_price
            for ticker, quote in quotes.items():
                old_entry = get_price(ticker)
                prev_price = old_entry["price"] if old_entry else (quote.prev_close or quote.price)
                set_price(ticker, quote.price, prev_price)

        except asyncio.CancelledError:
            logger.info("Market data task stopped")
            break
        except Exception as exc:
            logger.error("Market data task error: %s", exc)
            await asyncio.sleep(1.0)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI application."""
    # Load environment variables from .env
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=env_path)
    logger.info("Environment loaded from %s", env_path)

    # Initialize the database (create tables + seed default data)
    init_db()
    logger.info("Database initialized at %s", os.getenv("DB_PATH", "db/finally.db"))

    # Start background tasks — stored locally so each lifespan instance is independent
    background_tasks: list[asyncio.Task] = []
    market_task = asyncio.create_task(market_data_task(), name="market-data")
    snapshot_task = asyncio.create_task(snapshot_background_task(), name="portfolio-snapshot")
    background_tasks.extend([market_task, snapshot_task])
    logger.info("Background tasks started: market-data, portfolio-snapshot")

    try:
        yield  # Application is running
    finally:
        # Shutdown: cancel background tasks
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        logger.info("Background tasks stopped. Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FinAlly API",
    description="AI-powered trading workstation — FastAPI backend",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins in development (frontend is same-origin in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Routers
# ---------------------------------------------------------------------------

from .routers import stream, portfolio, watchlist, chat  # noqa: E402

app.include_router(stream.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Docker/deployment monitoring."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Static file serving (Next.js build output)
# ---------------------------------------------------------------------------

# Mount static files last so API routes take precedence
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    logger.info("Serving frontend static files from %s", static_dir)
else:
    logger.warning(
        "Static directory not found at %s — frontend will not be served. "
        "Run the Next.js build first.",
        static_dir,
    )
