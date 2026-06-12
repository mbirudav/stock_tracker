"""
API endpoint tests for FinAlly backend.

Uses FastAPI TestClient with an isolated temp SQLite database.
LLM_MOCK=true is set for all tests to avoid network calls.
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_env(tmp_path: Path, monkeypatch):
    """Set required environment variables for tests."""
    db_path = str(tmp_path / "test_finally.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MASSIVE_API_KEY", "")  # Use simulator
    yield


@pytest.fixture()
def client(set_env):
    """Return a TestClient with a fresh database."""
    # Import after env vars are set
    from backend.db.database import init_db
    init_db()

    from backend.main import app
    # Prime the price cache for default tickers
    from backend.price_cache import initialize_ticker
    default_tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
    for ticker in default_tickers:
        initialize_ticker(ticker, seed_price=100.0)

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_response_shape(self, client: TestClient) -> None:
        data = client.get("/api/health").json()
        assert data["status"] == "ok"
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------

class TestPortfolio:
    def test_get_portfolio_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/portfolio")
        assert response.status_code == 200

    def test_get_portfolio_shape(self, client: TestClient) -> None:
        data = client.get("/api/portfolio").json()
        assert "cash_balance" in data
        assert "positions" in data
        assert "total_value" in data
        assert isinstance(data["positions"], list)

    def test_get_portfolio_initial_cash(self, client: TestClient) -> None:
        data = client.get("/api/portfolio").json()
        assert abs(data["cash_balance"] - 10000.0) < 0.01

    def test_get_portfolio_history_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/portfolio/history")
        assert response.status_code == 200

    def test_get_portfolio_history_shape(self, client: TestClient) -> None:
        data = client.get("/api/portfolio/history").json()
        assert "snapshots" in data
        assert isinstance(data["snapshots"], list)


# ---------------------------------------------------------------------------
# Trade endpoint
# ---------------------------------------------------------------------------

class TestTrade:
    def test_buy_creates_position(self, client: TestClient) -> None:
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "buy"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Cash should have decreased
        portfolio = data["portfolio"]
        assert portfolio["cash_balance"] < 10000.0
        # Position should exist
        tickers = [p["ticker"] for p in portfolio["positions"]]
        assert "AAPL" in tickers

    def test_buy_decreases_cash(self, client: TestClient) -> None:
        # Buy 10 shares at $100 each = $1000 cost
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 10, "side": "buy"},
        )
        data = response.json()
        assert data["success"] is True
        portfolio = data["portfolio"]
        assert portfolio["cash_balance"] < 10000.0

    def test_buy_with_insufficient_cash_returns_400(self, client: TestClient) -> None:
        from backend.price_cache import initialize_ticker
        # Set a very high price so we can't afford it
        initialize_ticker("HIGHPRICE", seed_price=20000.0)
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "HIGHPRICE", "quantity": 1, "side": "buy"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["success"] is False
        assert "Insufficient cash" in data["detail"]["error"]

    def test_sell_more_than_owned_returns_400(self, client: TestClient) -> None:
        # Try to sell AAPL without owning any
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 100, "side": "sell"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["success"] is False
        assert "Insufficient shares" in data["detail"]["error"]

    def test_buy_then_sell_updates_position(self, client: TestClient) -> None:
        # Buy 10 shares
        client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 10, "side": "buy"},
        )
        # Sell 5 shares
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "sell"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should have 5 shares left
        portfolio = data["portfolio"]
        aapl_pos = next((p for p in portfolio["positions"] if p["ticker"] == "AAPL"), None)
        assert aapl_pos is not None
        assert abs(aapl_pos["quantity"] - 5.0) < 0.001

    def test_sell_all_removes_position(self, client: TestClient) -> None:
        # Buy 5 shares
        client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "buy"},
        )
        # Sell all 5
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "sell"},
        )
        assert response.status_code == 200
        portfolio = response.json()["portfolio"]
        aapl_pos = next((p for p in portfolio["positions"] if p["ticker"] == "AAPL"), None)
        assert aapl_pos is None

    def test_trade_response_shape(self, client: TestClient) -> None:
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 1, "side": "buy"},
        )
        data = response.json()
        assert "success" in data
        assert "trade" in data
        assert "portfolio" in data
        trade = data["trade"]
        assert "ticker" in trade
        assert "side" in trade
        assert "quantity" in trade
        assert "price" in trade
        assert "executed_at" in trade

    def test_invalid_side_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 1, "side": "hold"},
        )
        assert response.status_code == 422

    def test_invalid_quantity_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": -5, "side": "buy"},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Watchlist endpoints
# ---------------------------------------------------------------------------

class TestWatchlist:
    def test_get_watchlist_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/watchlist")
        assert response.status_code == 200

    def test_get_watchlist_returns_default_tickers(self, client: TestClient) -> None:
        data = client.get("/api/watchlist").json()
        assert "tickers" in data
        tickers = [t["ticker"] for t in data["tickers"]]
        assert "AAPL" in tickers

    def test_get_watchlist_includes_price(self, client: TestClient) -> None:
        data = client.get("/api/watchlist").json()
        for ticker_entry in data["tickers"]:
            # Price should be present (we pre-initialized in fixture)
            assert "ticker" in ticker_entry
            assert "price" in ticker_entry

    def test_add_ticker_returns_200(self, client: TestClient) -> None:
        response = client.post("/api/watchlist", json={"ticker": "AMD"})
        assert response.status_code == 200

    def test_add_ticker_appears_in_watchlist(self, client: TestClient) -> None:
        client.post("/api/watchlist", json={"ticker": "AMD"})
        data = client.get("/api/watchlist").json()
        tickers = [t["ticker"] for t in data["tickers"]]
        assert "AMD" in tickers

    def test_add_ticker_case_insensitive(self, client: TestClient) -> None:
        client.post("/api/watchlist", json={"ticker": "amd"})
        data = client.get("/api/watchlist").json()
        tickers = [t["ticker"] for t in data["tickers"]]
        assert "AMD" in tickers

    def test_add_duplicate_ticker_is_idempotent(self, client: TestClient) -> None:
        client.post("/api/watchlist", json={"ticker": "AAPL"})
        client.post("/api/watchlist", json={"ticker": "AAPL"})
        data = client.get("/api/watchlist").json()
        tickers = [t["ticker"] for t in data["tickers"]]
        assert tickers.count("AAPL") == 1

    def test_delete_ticker_returns_200(self, client: TestClient) -> None:
        response = client.delete("/api/watchlist/AAPL")
        assert response.status_code == 200

    def test_delete_ticker_removes_from_watchlist(self, client: TestClient) -> None:
        client.delete("/api/watchlist/AAPL")
        data = client.get("/api/watchlist").json()
        tickers = [t["ticker"] for t in data["tickers"]]
        assert "AAPL" not in tickers

    def test_delete_nonexistent_ticker_returns_404(self, client: TestClient) -> None:
        response = client.delete("/api/watchlist/ZZZNOTREAL")
        assert response.status_code == 404

    def test_watchlist_count_after_add_remove(self, client: TestClient) -> None:
        initial = len(client.get("/api/watchlist").json()["tickers"])
        client.post("/api/watchlist", json={"ticker": "AMD"})
        after_add = len(client.get("/api/watchlist").json()["tickers"])
        assert after_add == initial + 1
        client.delete("/api/watchlist/AMD")
        after_remove = len(client.get("/api/watchlist").json()["tickers"])
        assert after_remove == initial
