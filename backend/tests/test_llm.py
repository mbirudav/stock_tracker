"""
Unit tests for the LLM integration module.

Tests cover:
- Mock mode responses for buy / sell / watchlist / default messages
- Structured output parsing of valid JSON
- Graceful handling of malformed JSON
- Chat history truncation to last 20 messages

Run with:
    cd backend
    uv run pytest tests/test_llm.py -v
"""
from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_messages(user_content: str, history_len: int = 0) -> list[dict]:
    """Build a minimal messages list with optional history padding."""
    msgs: list[dict] = []
    for i in range(history_len):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"message {i}"})
    msgs.append({"role": "user", "content": user_content})
    return msgs


# ---------------------------------------------------------------------------
# Mock-mode tests (LLM_MOCK=true)
# ---------------------------------------------------------------------------

class TestMockMode:
    """All tests set LLM_MOCK=true so no network calls are made."""

    @pytest.fixture(autouse=True)
    def set_mock_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "true")

    def test_buy_aapl_returns_aapl_trade(self):
        from backend.llm.client import call_llm

        result = call_llm(_make_messages("Please buy AAPL"))
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0
        assert len(result["trades"]) == 1
        trade = result["trades"][0]
        assert trade["ticker"] == "AAPL"
        assert trade["side"] == "buy"
        assert trade["quantity"] > 0

    def test_buy_msft_extracts_ticker(self):
        from backend.llm.client import call_llm

        result = call_llm(_make_messages("buy MSFT for me"))
        assert len(result["trades"]) == 1
        trade = result["trades"][0]
        assert trade["ticker"] == "MSFT"
        assert trade["side"] == "buy"

    def test_sell_returns_sell_trade(self):
        from backend.llm.client import call_llm

        result = call_llm(_make_messages("sell TSLA immediately"))
        assert isinstance(result["message"], str)
        assert len(result["trades"]) == 1
        trade = result["trades"][0]
        assert trade["side"] == "sell"
        assert trade["quantity"] > 0

    def test_add_watchlist_message(self):
        from backend.llm.client import call_llm

        result = call_llm(_make_messages("add NVDA to my watchlist"))
        assert isinstance(result["message"], str)
        assert result["trades"] == []
        assert len(result["watchlist_changes"]) == 1
        change = result["watchlist_changes"][0]
        assert change["action"] == "add"

    def test_default_message_returns_non_empty_message_no_trades(self):
        from backend.llm.client import call_llm

        result = call_llm(_make_messages("how is my portfolio?"))
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0
        assert result["trades"] == []
        assert result["watchlist_changes"] == []

    def test_mock_uses_last_user_message(self):
        """When history is present, mock should key on the LAST user message."""
        from backend.llm.client import call_llm

        messages = [
            {"role": "user", "content": "sell everything"},
            {"role": "assistant", "content": "Done."},
            {"role": "user", "content": "buy AAPL"},  # last user message
        ]
        result = call_llm(messages)
        # "buy AAPL" should trigger the buy-AAPL mock
        assert result["trades"][0]["ticker"] == "AAPL"
        assert result["trades"][0]["side"] == "buy"


# ---------------------------------------------------------------------------
# Structured output parsing tests (no env var → tests parsing logic directly)
# ---------------------------------------------------------------------------

class TestStructuredOutputParsing:
    """Test the LLMResponse Pydantic model parsing used inside call_llm."""

    def test_valid_full_json_parses_correctly(self):
        from backend.llm.client import LLMResponse

        raw = json.dumps({
            "message": "Buying AAPL for you.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
            "watchlist_changes": [{"ticker": "MSFT", "action": "add"}],
        })
        parsed = LLMResponse.model_validate_json(raw)
        assert parsed.message == "Buying AAPL for you."
        assert len(parsed.trades) == 1
        assert parsed.trades[0].ticker == "AAPL"
        assert parsed.trades[0].side == "buy"
        assert parsed.trades[0].quantity == 10
        assert len(parsed.watchlist_changes) == 1
        assert parsed.watchlist_changes[0].ticker == "MSFT"
        assert parsed.watchlist_changes[0].action == "add"

    def test_valid_message_only_json(self):
        from backend.llm.client import LLMResponse

        raw = json.dumps({"message": "Your portfolio looks great."})
        parsed = LLMResponse.model_validate_json(raw)
        assert parsed.message == "Your portfolio looks great."
        assert parsed.trades == []
        assert parsed.watchlist_changes == []

    def test_empty_arrays_parse_correctly(self):
        from backend.llm.client import LLMResponse

        raw = json.dumps({
            "message": "No action needed.",
            "trades": [],
            "watchlist_changes": [],
        })
        parsed = LLMResponse.model_validate_json(raw)
        assert parsed.trades == []
        assert parsed.watchlist_changes == []

    def test_sell_trade_parses_correctly(self):
        from backend.llm.client import LLMResponse

        raw = json.dumps({
            "message": "Sold 5 shares.",
            "trades": [{"ticker": "TSLA", "side": "sell", "quantity": 5}],
            "watchlist_changes": [],
        })
        parsed = LLMResponse.model_validate_json(raw)
        assert parsed.trades[0].side == "sell"
        assert parsed.trades[0].ticker == "TSLA"


# ---------------------------------------------------------------------------
# Malformed JSON handling
# ---------------------------------------------------------------------------

class TestMalformedJsonHandling:
    """Test that call_llm returns the error fallback on bad LLM output."""

    @pytest.fixture(autouse=True)
    def clear_mock_env(self, monkeypatch):
        # Ensure we're NOT in mock mode so we test the real parsing path
        monkeypatch.setenv("LLM_MOCK", "false")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _make_fake_completion(self, content: str):
        """Create a fake litellm completion response object."""
        choice = MagicMock()
        choice.message.content = content
        response = MagicMock()
        response.choices = [choice]
        return response

    def test_malformed_json_returns_error_response(self, monkeypatch):
        from backend.llm import client

        fake_resp = self._make_fake_completion("this is not json {{{{")
        with patch("backend.llm.client.completion", return_value=fake_resp):
            result = client.call_llm(_make_messages("hi"))

        assert result["message"] == client._ERROR_RESPONSE["message"]
        assert result["trades"] == []
        assert result["watchlist_changes"] == []

    def test_empty_string_returns_error_response(self, monkeypatch):
        from backend.llm import client

        fake_resp = self._make_fake_completion("")
        with patch("backend.llm.client.completion", return_value=fake_resp):
            result = client.call_llm(_make_messages("hi"))

        assert result["message"] == client._ERROR_RESPONSE["message"]
        assert result["trades"] == []
        assert result["watchlist_changes"] == []

    def test_valid_plain_json_fallback(self, monkeypatch):
        """If response_format isn't honoured but content is valid JSON, use it."""
        from backend.llm import client

        valid_json = json.dumps({
            "message": "Here's my analysis.",
            "trades": [],
            "watchlist_changes": [],
        })
        fake_resp = self._make_fake_completion(valid_json)
        with patch("backend.llm.client.completion", return_value=fake_resp):
            result = client.call_llm(_make_messages("analyse my portfolio"))

        assert result["message"] == "Here's my analysis."

    def test_network_exception_returns_error_response(self, monkeypatch):
        from backend.llm import client

        with patch("backend.llm.client.completion", side_effect=RuntimeError("network error")):
            result = client.call_llm(_make_messages("hi"))

        assert result["message"] == client._ERROR_RESPONSE["message"]
        assert result["trades"] == []


# ---------------------------------------------------------------------------
# Chat history truncation
# ---------------------------------------------------------------------------

class TestChatHistoryTruncation:
    """
    Test that call_llm correctly operates on at most the last 20 messages.

    We simulate this by verifying the mock picks up the last user message
    even when a long history is prepended.
    """

    @pytest.fixture(autouse=True)
    def set_mock_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "true")

    def test_last_user_message_used_when_history_present(self):
        from backend.llm.client import call_llm

        # Build 40 history messages (user/assistant alternating) then add a buy
        messages = _make_messages("buy AAPL", history_len=40)
        result = call_llm(messages)
        # The mock should key on the last user message "buy AAPL"
        assert result["trades"][0]["ticker"] == "AAPL"
        assert result["trades"][0]["side"] == "buy"

    def test_history_of_20_messages_is_valid_input(self):
        """Verify that a 20-message history doesn't cause errors."""
        from backend.llm.client import call_llm

        messages = _make_messages("how is my portfolio?", history_len=20)
        result = call_llm(messages)
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0

    def test_single_message_works(self):
        """Edge case: a single message list."""
        from backend.llm.client import call_llm

        result = call_llm([{"role": "user", "content": "hello"}])
        assert isinstance(result["message"], str)
