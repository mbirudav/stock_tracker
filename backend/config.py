from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderConfig:
    api_key: str = ""
    rate_limit_per_minute: int = 60
    base_url: str = ""
    timeout: int = 30
    enabled: bool = True


@dataclass
class Config:
    # Provider configurations
    yahoo: ProviderConfig = field(
        default_factory=lambda: ProviderConfig(
            rate_limit_per_minute=60,
            enabled=True,
        )
    )
    alpha_vantage: ProviderConfig = field(
        default_factory=lambda: ProviderConfig(
            api_key=os.environ.get("ALPHA_VANTAGE_KEY", "demo"),
            rate_limit_per_minute=5,
            base_url="https://www.alphavantage.co/query",
            enabled=bool(os.environ.get("ALPHA_VANTAGE_KEY")),
        )
    )
    polygon: ProviderConfig = field(
        default_factory=lambda: ProviderConfig(
            api_key=os.environ.get("POLYGON_KEY", ""),
            rate_limit_per_minute=100,
            base_url="https://api.polygon.io",
            enabled=bool(os.environ.get("POLYGON_KEY")),
        )
    )
    finnhub: ProviderConfig = field(
        default_factory=lambda: ProviderConfig(
            api_key=os.environ.get("FINNHUB_KEY", ""),
            rate_limit_per_minute=30,
            base_url="https://finnhub.io/api/v1",
            enabled=bool(os.environ.get("FINNHUB_KEY")),
        )
    )

    # Cache settings
    cache_ttl_quote: float = 15.0         # seconds - quotes change frequently
    cache_ttl_history: float = 300.0      # 5 minutes
    cache_ttl_company: float = 3600.0     # 1 hour
    cache_ttl_news: float = 300.0         # 5 minutes
    cache_ttl_earnings: float = 3600.0    # 1 hour
    cache_ttl_financials: float = 3600.0  # 1 hour
    cache_ttl_movers: float = 60.0        # 1 minute
    cache_max_size: int = 2000

    # Request settings
    max_retries: int = 3
    retry_backoff: float = 1.0    # seconds between retries (doubles each time)

    # Default provider order (first is primary, rest are fallbacks)
    provider_order: list = field(
        default_factory=lambda: ["yahoo_finance", "alpha_vantage", "polygon", "finnhub"]
    )


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(cfg: Config) -> None:
    global _config
    _config = cfg
