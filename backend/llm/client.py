"""
LLM integration for FinAlly.

Calls openrouter/openai/gpt-oss-120b via LiteLLM + OpenRouter with Cerebras
as the inference provider. Returns structured JSON matching RESPONSE_SCHEMA.

Mock mode: set LLM_MOCK=true in environment for deterministic responses
(no API key needed — used for E2E tests and local dev).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from litellm import completion
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model / provider config
# ---------------------------------------------------------------------------

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}

# ---------------------------------------------------------------------------
# Structured output schema (Pydantic + plain dict for documentation)
# ---------------------------------------------------------------------------

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "trades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "quantity": {"type": "number"},
                },
                "required": ["ticker", "side", "quantity"],
            },
        },
        "watchlist_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "remove"]},
                },
                "required": ["ticker", "action"],
            },
        },
    },
    "required": ["message"],
}


class TradeAction(BaseModel):
    ticker: str
    side: str  # "buy" | "sell"
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: str  # "add" | "remove"


class LLMResponse(BaseModel):
    message: str
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Error fallback
# ---------------------------------------------------------------------------

_ERROR_RESPONSE: dict[str, Any] = {
    "message": "I encountered an error processing your request.",
    "trades": [],
    "watchlist_changes": [],
}


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------

def _mock_response(user_message: str) -> dict[str, Any]:
    """
    Return deterministic mock responses keyed on message content.
    Used when LLM_MOCK=true for E2E tests and offline development.
    """
    msg = user_message.lower()

    if "buy aapl" in msg:
        return {
            "message": "Buying 5 shares of AAPL for you.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5}],
            "watchlist_changes": [],
        }
    elif "buy" in msg:
        # Try to extract a ticker symbol (uppercase word after "buy")
        words = user_message.upper().split()
        buy_idx = next((i for i, w in enumerate(words) if w == "BUY"), None)
        ticker = words[buy_idx + 1] if buy_idx is not None and buy_idx + 1 < len(words) else "AAPL"
        # Strip punctuation
        ticker = "".join(c for c in ticker if c.isalpha())[:5] or "AAPL"
        return {
            "message": f"Buying 5 shares of {ticker} for you.",
            "trades": [{"ticker": ticker, "side": "buy", "quantity": 5}],
            "watchlist_changes": [],
        }
    elif "sell" in msg:
        # Try to extract a ticker symbol (uppercase word after "sell")
        words = user_message.upper().split()
        sell_idx = next((i for i, w in enumerate(words) if w == "SELL"), None)
        ticker = words[sell_idx + 1] if sell_idx is not None and sell_idx + 1 < len(words) else "AAPL"
        ticker = "".join(c for c in ticker if c.isalpha())[:5] or "AAPL"
        return {
            "message": f"Selling shares of {ticker} as requested.",
            "trades": [{"ticker": ticker, "side": "sell", "quantity": 5}],
            "watchlist_changes": [],
        }
    elif "add" in msg and "watchlist" in msg:
        return {
            "message": "Added TSLA to your watchlist.",
            "trades": [],
            "watchlist_changes": [{"ticker": "TSLA", "action": "add"}],
        }
    elif "remove" in msg and "watchlist" in msg:
        return {
            "message": "Removed the ticker from your watchlist.",
            "trades": [],
            "watchlist_changes": [{"ticker": "TSLA", "action": "remove"}],
        }
    else:
        return {
            "message": (
                "Your portfolio looks balanced. AAPL is your largest position at 40% weight. "
                "Consider diversifying into JPM for sector balance."
            ),
            "trades": [],
            "watchlist_changes": [],
        }


# ---------------------------------------------------------------------------
# Main call
# ---------------------------------------------------------------------------

def call_llm(messages: list[dict]) -> dict[str, Any]:
    """
    Call the LLM and return a structured response dict.

    Args:
        messages: OpenAI-format message list (role + content dicts).
                  Must include at least the user's message as the last item.

    Returns:
        dict with keys: message (str), trades (list), watchlist_changes (list).
        On any error, returns _ERROR_RESPONSE.
    """
    # ------------------------------------------------------------------
    # Mock mode — no network call, fast + free
    # ------------------------------------------------------------------
    if os.getenv("LLM_MOCK", "").lower() == "true":
        # Use the last user message for keyword matching
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break
        return _mock_response(last_user_msg)

    # ------------------------------------------------------------------
    # Real LLM call
    # ------------------------------------------------------------------
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.error("OPENROUTER_API_KEY is not set")
        return _ERROR_RESPONSE

    try:
        response = completion(
            model=MODEL,
            messages=messages,
            response_format=LLMResponse,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
            api_key=api_key,
            api_base="https://openrouter.ai/api/v1",
        )
        raw = response.choices[0].message.content

        # Parse and validate via Pydantic
        parsed = LLMResponse.model_validate_json(raw)
        return {
            "message": parsed.message,
            "trades": [t.model_dump() for t in parsed.trades],
            "watchlist_changes": [w.model_dump() for w in parsed.watchlist_changes],
        }

    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM call failed: %s", exc)

        # Attempt a plain JSON parse as last resort (in case response_format
        # isn't honoured by the provider and we got raw JSON text anyway)
        try:
            raw_content = response.choices[0].message.content  # type: ignore[possibly-undefined]
            data = json.loads(raw_content)
            return {
                "message": data.get("message", _ERROR_RESPONSE["message"]),
                "trades": data.get("trades", []),
                "watchlist_changes": data.get("watchlist_changes", []),
            }
        except Exception:
            return dict(_ERROR_RESPONSE)
