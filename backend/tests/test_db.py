"""
Unit tests for the FinAlly database layer.

Each test function receives a fresh SQLite database in a temp directory via
the `db_path` fixture, so tests are fully isolated and leave no files behind.
"""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from backend.db.database import init_db, get_db
from backend.db import crud


# ---------------------------------------------------------------------------
# Fixture: fresh isolated database for every test
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    """Return the path to a freshly initialised SQLite database."""
    path = str(tmp_path / "test_finally.db")
    init_db(path)
    return path


# ---------------------------------------------------------------------------
# Task #4 – Schema creation
# ---------------------------------------------------------------------------

class TestSchemaCreation:
    """Verify that init_db creates all 6 expected tables."""

    EXPECTED_TABLES = {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    }

    def test_all_tables_exist(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {row["name"] for row in rows}
        assert self.EXPECTED_TABLES.issubset(tables), (
            f"Missing tables: {self.EXPECTED_TABLES - tables}"
        )

    def test_users_profile_columns(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            info = conn.execute("PRAGMA table_info(users_profile)").fetchall()
            cols = {r["name"] for r in info}
        assert {"id", "cash_balance", "created_at"}.issubset(cols)

    def test_watchlist_columns(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            info = conn.execute("PRAGMA table_info(watchlist)").fetchall()
            cols = {r["name"] for r in info}
        assert {"id", "user_id", "ticker", "added_at"}.issubset(cols)

    def test_positions_columns(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            info = conn.execute("PRAGMA table_info(positions)").fetchall()
            cols = {r["name"] for r in info}
        assert {"id", "user_id", "ticker", "quantity", "avg_cost", "updated_at"}.issubset(cols)

    def test_trades_columns(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            info = conn.execute("PRAGMA table_info(trades)").fetchall()
            cols = {r["name"] for r in info}
        assert {"id", "user_id", "ticker", "side", "quantity", "price", "executed_at"}.issubset(cols)

    def test_portfolio_snapshots_columns(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            info = conn.execute("PRAGMA table_info(portfolio_snapshots)").fetchall()
            cols = {r["name"] for r in info}
        assert {"id", "user_id", "total_value", "recorded_at"}.issubset(cols)

    def test_chat_messages_columns(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            info = conn.execute("PRAGMA table_info(chat_messages)").fetchall()
            cols = {r["name"] for r in info}
        assert {"id", "user_id", "role", "content", "actions", "created_at"}.issubset(cols)

    def test_wal_mode_enabled(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_init_db_is_idempotent(self, db_path: str) -> None:
        """Calling init_db twice on the same file must not raise or duplicate data."""
        init_db(db_path)  # second call
        with get_db(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# Task #4 – Seed data
# ---------------------------------------------------------------------------

class TestSeedData:
    """Verify that the default user and watchlist are seeded correctly."""

    DEFAULT_TICKERS = {
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    }

    def test_default_user_exists(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            row = conn.execute(
                "SELECT id, cash_balance FROM users_profile WHERE id='default'"
            ).fetchone()
        assert row is not None
        assert row["id"] == "default"
        assert float(row["cash_balance"]) == pytest.approx(10000.0)

    def test_default_watchlist_count(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM watchlist WHERE user_id='default'"
            ).fetchone()[0]
        assert count == 10

    def test_default_watchlist_tickers(self, db_path: str) -> None:
        with get_db(db_path) as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlist WHERE user_id='default'"
            ).fetchall()
        seeded = {r["ticker"] for r in rows}
        assert seeded == self.DEFAULT_TICKERS

    def test_seed_not_duplicated_on_reinit(self, db_path: str) -> None:
        """Running init_db again must not insert duplicate seed rows."""
        init_db(db_path)
        with get_db(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM watchlist WHERE user_id='default'").fetchone()[0]
        assert count == 10


# ---------------------------------------------------------------------------
# Task #4 – Cash balance get / update
# ---------------------------------------------------------------------------

class TestCashBalance:
    def test_get_cash_balance_default(self, db_path: str) -> None:
        balance = crud.get_cash_balance("default", db_path=db_path)
        assert balance == pytest.approx(10000.0)

    def test_update_cash_balance(self, db_path: str) -> None:
        crud.update_cash_balance("default", 7500.50, db_path=db_path)
        balance = crud.get_cash_balance("default", db_path=db_path)
        assert balance == pytest.approx(7500.50)

    def test_update_cash_balance_to_zero(self, db_path: str) -> None:
        crud.update_cash_balance("default", 0.0, db_path=db_path)
        assert crud.get_cash_balance("default", db_path=db_path) == pytest.approx(0.0)

    def test_get_cash_balance_missing_user_raises(self, db_path: str) -> None:
        with pytest.raises(ValueError, match="not found"):
            crud.get_cash_balance("nonexistent_user", db_path=db_path)


# ---------------------------------------------------------------------------
# Task #4 – Watchlist add / remove / get
# ---------------------------------------------------------------------------

class TestWatchlist:
    def test_get_watchlist_returns_seeded_tickers(self, db_path: str) -> None:
        tickers = crud.get_watchlist("default", db_path=db_path)
        assert len(tickers) == 10
        assert "AAPL" in tickers

    def test_add_ticker(self, db_path: str) -> None:
        crud.add_to_watchlist("default", "PYPL", db_path=db_path)
        tickers = crud.get_watchlist("default", db_path=db_path)
        assert "PYPL" in tickers
        assert len(tickers) == 11

    def test_add_ticker_uppercases(self, db_path: str) -> None:
        crud.add_to_watchlist("default", "amd", db_path=db_path)
        tickers = crud.get_watchlist("default", db_path=db_path)
        assert "AMD" in tickers

    def test_add_duplicate_is_noop(self, db_path: str) -> None:
        crud.add_to_watchlist("default", "AAPL", db_path=db_path)
        tickers = crud.get_watchlist("default", db_path=db_path)
        assert tickers.count("AAPL") == 1

    def test_remove_ticker(self, db_path: str) -> None:
        crud.remove_from_watchlist("default", "AAPL", db_path=db_path)
        tickers = crud.get_watchlist("default", db_path=db_path)
        assert "AAPL" not in tickers
        assert len(tickers) == 9

    def test_remove_nonexistent_is_noop(self, db_path: str) -> None:
        crud.remove_from_watchlist("default", "ZZZZ", db_path=db_path)
        tickers = crud.get_watchlist("default", db_path=db_path)
        assert len(tickers) == 10  # unchanged

    def test_watchlist_ordered_by_added_at(self, db_path: str) -> None:
        """Tickers should be returned in insertion order (added_at ASC)."""
        crud.add_to_watchlist("default", "AMD", db_path=db_path)
        tickers = crud.get_watchlist("default", db_path=db_path)
        assert tickers[-1] == "AMD"


# ---------------------------------------------------------------------------
# Task #4 – Position upsert and delete when quantity=0
# ---------------------------------------------------------------------------

class TestPositions:
    def test_get_positions_empty_initially(self, db_path: str) -> None:
        positions = crud.get_positions("default", db_path=db_path)
        assert positions == []

    def test_upsert_creates_position(self, db_path: str) -> None:
        crud.upsert_position("default", "AAPL", 10.0, 150.0, db_path=db_path)
        positions = crud.get_positions("default", db_path=db_path)
        assert len(positions) == 1
        pos = positions[0]
        assert pos["ticker"] == "AAPL"
        assert pos["quantity"] == pytest.approx(10.0)
        assert pos["avg_cost"] == pytest.approx(150.0)

    def test_upsert_updates_existing_position(self, db_path: str) -> None:
        crud.upsert_position("default", "AAPL", 10.0, 150.0, db_path=db_path)
        crud.upsert_position("default", "AAPL", 15.0, 155.0, db_path=db_path)
        positions = crud.get_positions("default", db_path=db_path)
        assert len(positions) == 1
        assert positions[0]["quantity"] == pytest.approx(15.0)
        assert positions[0]["avg_cost"] == pytest.approx(155.0)

    def test_upsert_zero_quantity_deletes_position(self, db_path: str) -> None:
        """Per spec: when quantity reaches 0, the position row is deleted."""
        crud.upsert_position("default", "AAPL", 10.0, 150.0, db_path=db_path)
        crud.upsert_position("default", "AAPL", 0.0, 150.0, db_path=db_path)
        positions = crud.get_positions("default", db_path=db_path)
        assert positions == []

    def test_upsert_negative_quantity_deletes_position(self, db_path: str) -> None:
        crud.upsert_position("default", "AAPL", 5.0, 150.0, db_path=db_path)
        crud.upsert_position("default", "AAPL", -1.0, 150.0, db_path=db_path)
        assert crud.get_positions("default", db_path=db_path) == []

    def test_delete_position(self, db_path: str) -> None:
        crud.upsert_position("default", "AAPL", 10.0, 150.0, db_path=db_path)
        crud.delete_position("default", "AAPL", db_path=db_path)
        assert crud.get_positions("default", db_path=db_path) == []

    def test_delete_nonexistent_position_is_noop(self, db_path: str) -> None:
        crud.delete_position("default", "ZZZZ", db_path=db_path)  # should not raise

    def test_multiple_positions(self, db_path: str) -> None:
        crud.upsert_position("default", "AAPL", 5.0, 150.0, db_path=db_path)
        crud.upsert_position("default", "TSLA", 3.0, 200.0, db_path=db_path)
        positions = crud.get_positions("default", db_path=db_path)
        tickers = [p["ticker"] for p in positions]
        assert "AAPL" in tickers
        assert "TSLA" in tickers

    def test_ticker_stored_uppercase(self, db_path: str) -> None:
        crud.upsert_position("default", "aapl", 5.0, 150.0, db_path=db_path)
        positions = crud.get_positions("default", db_path=db_path)
        assert positions[0]["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# Task #4 – Trade insert returns UUID
# ---------------------------------------------------------------------------

class TestTrades:
    def test_insert_trade_returns_uuid(self, db_path: str) -> None:
        trade_id = crud.insert_trade("default", "AAPL", "buy", 10.0, 150.0, db_path=db_path)
        # Must be a valid UUID4 string
        parsed = uuid.UUID(trade_id, version=4)
        assert str(parsed) == trade_id

    def test_insert_buy_trade(self, db_path: str) -> None:
        crud.insert_trade("default", "AAPL", "buy", 10.0, 150.0, db_path=db_path)
        with get_db(db_path) as conn:
            row = conn.execute("SELECT * FROM trades").fetchone()
        assert row["side"] == "buy"
        assert row["ticker"] == "AAPL"
        assert float(row["quantity"]) == pytest.approx(10.0)
        assert float(row["price"]) == pytest.approx(150.0)

    def test_insert_sell_trade(self, db_path: str) -> None:
        crud.insert_trade("default", "TSLA", "sell", 5.0, 250.0, db_path=db_path)
        with get_db(db_path) as conn:
            row = conn.execute("SELECT * FROM trades WHERE side='sell'").fetchone()
        assert row is not None
        assert row["ticker"] == "TSLA"

    def test_insert_trade_invalid_side_raises(self, db_path: str) -> None:
        with pytest.raises(ValueError, match="side must be"):
            crud.insert_trade("default", "AAPL", "hold", 1.0, 100.0, db_path=db_path)

    def test_multiple_trades_persisted(self, db_path: str) -> None:
        for i in range(3):
            crud.insert_trade("default", "AAPL", "buy", float(i + 1), 150.0 + i, db_path=db_path)
        with get_db(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        assert count == 3

    def test_trade_ids_are_unique(self, db_path: str) -> None:
        id1 = crud.insert_trade("default", "AAPL", "buy", 1.0, 100.0, db_path=db_path)
        id2 = crud.insert_trade("default", "AAPL", "buy", 2.0, 101.0, db_path=db_path)
        assert id1 != id2


# ---------------------------------------------------------------------------
# Task #4 – Portfolio snapshot insert and query
# ---------------------------------------------------------------------------

class TestPortfolioSnapshots:
    def test_insert_snapshot(self, db_path: str) -> None:
        crud.insert_snapshot("default", 10500.0, db_path=db_path)
        with get_db(db_path) as conn:
            row = conn.execute("SELECT total_value FROM portfolio_snapshots").fetchone()
        assert float(row["total_value"]) == pytest.approx(10500.0)

    def test_get_snapshots_returns_list(self, db_path: str) -> None:
        crud.insert_snapshot("default", 10000.0, db_path=db_path)
        crud.insert_snapshot("default", 10100.0, db_path=db_path)
        snapshots = crud.get_snapshots("default", db_path=db_path)
        assert len(snapshots) == 2

    def test_get_snapshots_chronological_order(self, db_path: str) -> None:
        """Snapshots should be returned oldest-first for charting."""
        for val in [10000.0, 10050.0, 10100.0]:
            crud.insert_snapshot("default", val, db_path=db_path)
        snapshots = crud.get_snapshots("default", db_path=db_path)
        values = [s["total_value"] for s in snapshots]
        assert values == sorted(values)

    def test_get_snapshots_respects_limit(self, db_path: str) -> None:
        for i in range(10):
            crud.insert_snapshot("default", 10000.0 + i, db_path=db_path)
        snapshots = crud.get_snapshots("default", limit=5, db_path=db_path)
        assert len(snapshots) == 5

    def test_get_snapshots_empty(self, db_path: str) -> None:
        snapshots = crud.get_snapshots("default", db_path=db_path)
        assert snapshots == []

    def test_snapshot_dict_keys(self, db_path: str) -> None:
        crud.insert_snapshot("default", 9999.0, db_path=db_path)
        snapshots = crud.get_snapshots("default", db_path=db_path)
        assert "total_value" in snapshots[0]
        assert "recorded_at" in snapshots[0]


# ---------------------------------------------------------------------------
# Task #4 – Chat message insert and retrieve last N
# ---------------------------------------------------------------------------

class TestChatMessages:
    def test_insert_message_returns_uuid(self, db_path: str) -> None:
        msg_id = crud.insert_message("default", "user", "Hello!", db_path=db_path)
        parsed = uuid.UUID(msg_id, version=4)
        assert str(parsed) == msg_id

    def test_insert_user_message(self, db_path: str) -> None:
        crud.insert_message("default", "user", "Buy 5 AAPL", db_path=db_path)
        with get_db(db_path) as conn:
            row = conn.execute("SELECT * FROM chat_messages WHERE role='user'").fetchone()
        assert row["content"] == "Buy 5 AAPL"
        assert row["role"] == "user"

    def test_insert_assistant_message_with_actions(self, db_path: str) -> None:
        actions_json = '{"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5}]}'
        crud.insert_message("default", "assistant", "Buying 5 AAPL for you.", actions=actions_json, db_path=db_path)
        with get_db(db_path) as conn:
            row = conn.execute("SELECT * FROM chat_messages WHERE role='assistant'").fetchone()
        assert row["actions"] == actions_json

    def test_insert_message_invalid_role_raises(self, db_path: str) -> None:
        with pytest.raises(ValueError, match="role must be"):
            crud.insert_message("default", "system", "test", db_path=db_path)

    def test_get_recent_messages_empty(self, db_path: str) -> None:
        messages = crud.get_recent_messages("default", db_path=db_path)
        assert messages == []

    def test_get_recent_messages_returns_all_when_under_limit(self, db_path: str) -> None:
        crud.insert_message("default", "user", "msg1", db_path=db_path)
        crud.insert_message("default", "assistant", "reply1", db_path=db_path)
        messages = crud.get_recent_messages("default", limit=20, db_path=db_path)
        assert len(messages) == 2

    def test_get_recent_messages_limit(self, db_path: str) -> None:
        """Only the most recent N messages should be returned."""
        for i in range(25):
            role = "user" if i % 2 == 0 else "assistant"
            crud.insert_message("default", role, f"message {i}", db_path=db_path)
        messages = crud.get_recent_messages("default", limit=20, db_path=db_path)
        assert len(messages) == 20

    def test_get_recent_messages_chronological_order(self, db_path: str) -> None:
        """Messages should be oldest-first (for LLM context window)."""
        crud.insert_message("default", "user", "first", db_path=db_path)
        crud.insert_message("default", "assistant", "second", db_path=db_path)
        messages = crud.get_recent_messages("default", limit=20, db_path=db_path)
        assert messages[0]["content"] == "first"
        assert messages[1]["content"] == "second"

    def test_get_recent_messages_returns_last_n_when_over_limit(self, db_path: str) -> None:
        """When more messages exist than the limit, the MOST RECENT ones are returned."""
        for i in range(25):
            crud.insert_message("default", "user", f"message {i}", db_path=db_path)
        messages = crud.get_recent_messages("default", limit=10, db_path=db_path)
        assert len(messages) == 10
        # The last returned message should be message 24 (most recent)
        assert messages[-1]["content"] == "message 24"

    def test_message_dict_keys(self, db_path: str) -> None:
        crud.insert_message("default", "user", "test", db_path=db_path)
        messages = crud.get_recent_messages("default", db_path=db_path)
        keys = set(messages[0].keys())
        assert {"id", "role", "content", "actions", "created_at"}.issubset(keys)

    def test_message_actions_none_by_default(self, db_path: str) -> None:
        crud.insert_message("default", "user", "just a question", db_path=db_path)
        messages = crud.get_recent_messages("default", db_path=db_path)
        assert messages[0]["actions"] is None
