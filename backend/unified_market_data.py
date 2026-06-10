"""
Unified Market Data Interface

Defines the abstract contract all market data providers must implement and
provides a UnifiedMarketData manager with caching and provider failover.
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    Analyst,
    CompanyInfo,
    CryptoQuote,
    DataProvider,
    Dividend,
    Earnings,
    EconomicIndicator,
    FinancialStatement,
    ForexRate,
    InsiderTransaction,
    Interval,
    MarketIndex,
    MarketMover,
    MarketStatus,
    NewsItem,
    OHLCV,
    OptionChain,
    Period,
    Quote,
    SectorPerformance,
    TechnicalIndicator,
)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class MarketDataProvider(ABC):
    """Abstract base class every market data provider must subclass."""

    @property
    @abstractmethod
    def provider_id(self) -> DataProvider:
        ...

    # ------------------------------------------------------------------
    # Required methods — all providers must implement these
    # ------------------------------------------------------------------

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Current best-effort quote for *symbol*."""
        ...

    @abstractmethod
    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Batch quotes. Providers that don't support batching may iterate."""
        ...

    @abstractmethod
    def get_historical(
        self,
        symbol: str,
        period: Period = Period.MONTH_1,
        interval: Interval = Interval.DAY_1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[OHLCV]:
        """OHLCV bars for *symbol*. Either *period* or *start/end* may be used."""
        ...

    @abstractmethod
    def get_company_info(self, symbol: str) -> CompanyInfo:
        """Company / security metadata."""
        ...

    @abstractmethod
    def get_news(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        """Latest news articles related to *symbol*."""
        ...

    # ------------------------------------------------------------------
    # Optional methods — subclasses override what they support
    # ------------------------------------------------------------------

    def get_options(self, symbol: str, expiry: Optional[datetime] = None) -> List[OptionChain]:
        raise NotImplementedError(f"{self.provider_id} does not provide options data")

    def get_earnings(self, symbol: str, quarters: int = 4) -> List[Earnings]:
        raise NotImplementedError(f"{self.provider_id} does not provide earnings data")

    def get_dividends(self, symbol: str) -> List[Dividend]:
        raise NotImplementedError(f"{self.provider_id} does not provide dividend data")

    def get_financials(
        self, symbol: str, period: str = "annual"
    ) -> List[FinancialStatement]:
        raise NotImplementedError(f"{self.provider_id} does not provide financial statements")

    def get_analyst_ratings(self, symbol: str) -> List[Analyst]:
        raise NotImplementedError(f"{self.provider_id} does not provide analyst ratings")

    def get_insider_transactions(self, symbol: str) -> List[InsiderTransaction]:
        raise NotImplementedError(f"{self.provider_id} does not provide insider data")

    def get_market_movers(
        self, category: str = "gainers", limit: int = 20
    ) -> List[MarketMover]:
        raise NotImplementedError(f"{self.provider_id} does not provide market movers")

    def get_market_indices(self) -> List[MarketIndex]:
        raise NotImplementedError(f"{self.provider_id} does not provide index data")

    def get_sector_performance(self) -> List[SectorPerformance]:
        raise NotImplementedError(f"{self.provider_id} does not provide sector data")

    def get_crypto_quote(self, symbol: str) -> CryptoQuote:
        raise NotImplementedError(f"{self.provider_id} does not provide crypto data")

    def get_forex_rate(self, base: str, quote: str) -> ForexRate:
        raise NotImplementedError(f"{self.provider_id} does not provide forex data")

    def get_technical_indicators(
        self, symbol: str, indicators: List[str], interval: Interval = Interval.DAY_1
    ) -> List[TechnicalIndicator]:
        raise NotImplementedError(f"{self.provider_id} does not provide technical indicators")

    def get_economic_indicators(self) -> List[EconomicIndicator]:
        raise NotImplementedError(f"{self.provider_id} does not provide economic indicators")

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        raise NotImplementedError(f"{self.provider_id} does not support symbol search")

    def get_market_status(self) -> MarketStatus:
        """Determine current US equity market status."""
        now = datetime.now()
        if now.weekday() >= 5:
            return MarketStatus.CLOSED
        hour_min = now.hour * 60 + now.minute
        if 240 <= hour_min < 570:       # 04:00 – 09:30 ET
            return MarketStatus.PRE_MARKET
        if 570 <= hour_min < 960:       # 09:30 – 16:00 ET
            return MarketStatus.OPEN
        if 960 <= hour_min < 1200:      # 16:00 – 20:00 ET
            return MarketStatus.AFTER_HOURS
        return MarketStatus.CLOSED

    def is_market_open(self) -> bool:
        return self.get_market_status() == MarketStatus.OPEN


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl


class _TTLCache:
    """Thread-safe cache with per-entry TTL and a max-size eviction policy."""

    def __init__(self, max_size: int = 2000, default_ttl: float = 60.0) -> None:
        self._store: Dict[str, _CacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        with self._lock:
            if len(self._store) >= self._max_size:
                # Evict soonest-to-expire entry
                victim = min(self._store, key=lambda k: self._store[k].expires_at)
                del self._store[victim]
            self._store[key] = _CacheEntry(value, ttl if ttl is not None else self._default_ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            victims = [k for k in self._store if k.startswith(prefix)]
            for k in victims:
                del self._store[k]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._store)


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Thread-safe registry mapping DataProvider ids to provider instances."""

    def __init__(self) -> None:
        self._providers: Dict[DataProvider, MarketDataProvider] = {}
        self._order: List[DataProvider] = []
        self._lock = threading.Lock()

    def register(self, provider: MarketDataProvider, primary: bool = False) -> None:
        with self._lock:
            pid = provider.provider_id
            self._providers[pid] = provider
            if pid in self._order:
                self._order.remove(pid)
            if primary:
                self._order.insert(0, pid)
            else:
                self._order.append(pid)

    def unregister(self, provider_id: DataProvider) -> None:
        with self._lock:
            self._providers.pop(provider_id, None)
            if provider_id in self._order:
                self._order.remove(provider_id)

    def get(self, provider_id: DataProvider) -> Optional[MarketDataProvider]:
        return self._providers.get(provider_id)

    def primary(self) -> Optional[MarketDataProvider]:
        with self._lock:
            if not self._order:
                return None
            return self._providers.get(self._order[0])

    def all_ordered(self) -> List[MarketDataProvider]:
        with self._lock:
            return [self._providers[pid] for pid in self._order if pid in self._providers]

    def set_order(self, order: List[DataProvider]) -> None:
        with self._lock:
            self._order = [pid for pid in order if pid in self._providers]


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------

class UnifiedMarketData:
    """
    Central market data hub.

    Wraps a ProviderRegistry and a TTLCache. Every public method attempts
    providers in registry order and falls back to the next on failure.
    Results are cached with configurable TTLs.
    """

    # Default TTLs (seconds) — can be overridden per-instance
    TTL_QUOTE = 15.0
    TTL_QUOTES = 15.0
    TTL_HISTORY = 300.0
    TTL_COMPANY = 3600.0
    TTL_NEWS = 300.0
    TTL_OPTIONS = 60.0
    TTL_EARNINGS = 3600.0
    TTL_DIVIDENDS = 3600.0
    TTL_FINANCIALS = 3600.0
    TTL_ANALYSTS = 3600.0
    TTL_INSIDER = 3600.0
    TTL_MOVERS = 60.0
    TTL_INDICES = 30.0
    TTL_SECTORS = 300.0
    TTL_CRYPTO = 30.0
    TTL_FOREX = 30.0

    def __init__(
        self,
        providers: Optional[List[MarketDataProvider]] = None,
        cache_max_size: int = 2000,
    ) -> None:
        self._registry = ProviderRegistry()
        self._cache = _TTLCache(max_size=cache_max_size)
        if providers:
            for i, p in enumerate(providers):
                self._registry.register(p, primary=(i == 0))

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def add_provider(self, provider: MarketDataProvider, primary: bool = False) -> None:
        self._registry.register(provider, primary=primary)

    def remove_provider(self, provider_id: DataProvider) -> None:
        self._registry.unregister(provider_id)

    def set_provider_order(self, order: List[DataProvider]) -> None:
        self._registry.set_order(order)

    def get_provider(self, provider_id: DataProvider) -> Optional[MarketDataProvider]:
        return self._registry.get(provider_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Call *method* on providers in order; raise if all fail."""
        errors: List[Tuple[DataProvider, Exception]] = []
        for provider in self._registry.all_ordered():
            fn = getattr(provider, method, None)
            if fn is None:
                continue
            try:
                return fn(*args, **kwargs)
            except NotImplementedError:
                continue
            except Exception as exc:
                errors.append((provider.provider_id, exc))
        if errors:
            detail = "; ".join(f"{pid}: {err}" for pid, err in errors)
            raise RuntimeError(f"All providers failed for '{method}': {detail}")
        raise RuntimeError(f"No provider available for '{method}'")

    def _cached_call(
        self, cache_key: str, ttl: float, method: str, *args: Any, **kwargs: Any
    ) -> Any:
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._call(method, *args, **kwargs)
        self._cache.set(cache_key, result, ttl=ttl)
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str, use_cache: bool = True) -> Quote:
        key = f"quote:{symbol.upper()}"
        if not use_cache:
            return self._call("get_quote", symbol)
        return self._cached_call(key, self.TTL_QUOTE, "get_quote", symbol)

    def get_quotes(self, symbols: List[str], use_cache: bool = True) -> Dict[str, Quote]:
        key = "quotes:" + ":".join(sorted(s.upper() for s in symbols))
        if not use_cache:
            return self._call("get_quotes", symbols)
        return self._cached_call(key, self.TTL_QUOTES, "get_quotes", symbols)

    def get_historical(
        self,
        symbol: str,
        period: Period = Period.MONTH_1,
        interval: Interval = Interval.DAY_1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        use_cache: bool = True,
    ) -> List[OHLCV]:
        key = f"hist:{symbol.upper()}:{period}:{interval}"
        if not use_cache:
            return self._call("get_historical", symbol, period, interval, start, end)
        return self._cached_call(
            key, self.TTL_HISTORY, "get_historical", symbol, period, interval, start, end
        )

    def get_company_info(self, symbol: str, use_cache: bool = True) -> CompanyInfo:
        key = f"company:{symbol.upper()}"
        if not use_cache:
            return self._call("get_company_info", symbol)
        return self._cached_call(key, self.TTL_COMPANY, "get_company_info", symbol)

    def get_news(
        self, symbol: str, limit: int = 20, use_cache: bool = True
    ) -> List[NewsItem]:
        key = f"news:{symbol.upper()}:{limit}"
        if not use_cache:
            return self._call("get_news", symbol, limit)
        return self._cached_call(key, self.TTL_NEWS, "get_news", symbol, limit)

    def get_options(
        self, symbol: str, expiry: Optional[datetime] = None
    ) -> List[OptionChain]:
        return self._call("get_options", symbol, expiry)

    def get_earnings(self, symbol: str, quarters: int = 4) -> List[Earnings]:
        key = f"earnings:{symbol.upper()}:{quarters}"
        return self._cached_call(key, self.TTL_EARNINGS, "get_earnings", symbol, quarters)

    def get_dividends(self, symbol: str) -> List[Dividend]:
        key = f"dividends:{symbol.upper()}"
        return self._cached_call(key, self.TTL_DIVIDENDS, "get_dividends", symbol)

    def get_financials(
        self, symbol: str, period: str = "annual"
    ) -> List[FinancialStatement]:
        key = f"financials:{symbol.upper()}:{period}"
        return self._cached_call(key, self.TTL_FINANCIALS, "get_financials", symbol, period)

    def get_analyst_ratings(self, symbol: str) -> List[Analyst]:
        key = f"analysts:{symbol.upper()}"
        return self._cached_call(key, self.TTL_ANALYSTS, "get_analyst_ratings", symbol)

    def get_insider_transactions(self, symbol: str) -> List[InsiderTransaction]:
        key = f"insider:{symbol.upper()}"
        return self._cached_call(
            key, self.TTL_INSIDER, "get_insider_transactions", symbol
        )

    def get_market_movers(
        self, category: str = "gainers", limit: int = 20
    ) -> List[MarketMover]:
        key = f"movers:{category}:{limit}"
        return self._cached_call(
            key, self.TTL_MOVERS, "get_market_movers", category, limit
        )

    def get_market_indices(self) -> List[MarketIndex]:
        return self._cached_call("indices", self.TTL_INDICES, "get_market_indices")

    def get_sector_performance(self) -> List[SectorPerformance]:
        return self._cached_call("sectors", self.TTL_SECTORS, "get_sector_performance")

    def get_crypto_quote(self, symbol: str) -> CryptoQuote:
        key = f"crypto:{symbol.upper()}"
        return self._cached_call(key, self.TTL_CRYPTO, "get_crypto_quote", symbol)

    def get_forex_rate(self, base: str, quote: str) -> ForexRate:
        key = f"forex:{base.upper()}:{quote.upper()}"
        return self._cached_call(key, self.TTL_FOREX, "get_forex_rate", base, quote)

    def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        interval: Interval = Interval.DAY_1,
    ) -> List[TechnicalIndicator]:
        return self._call("get_technical_indicators", symbol, indicators, interval)

    def get_economic_indicators(self) -> List[EconomicIndicator]:
        return self._cached_call(
            "economic", 3600.0, "get_economic_indicators"
        )

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        return self._call("search_symbols", query, limit)

    def get_market_status(self) -> MarketStatus:
        primary = self._registry.primary()
        if primary:
            return primary.get_market_status()
        # fallback: derive from system time
        now = datetime.now()
        if now.weekday() >= 5:
            return MarketStatus.CLOSED
        hour_min = now.hour * 60 + now.minute
        if 570 <= hour_min < 960:
            return MarketStatus.OPEN
        if 240 <= hour_min < 570:
            return MarketStatus.PRE_MARKET
        if 960 <= hour_min < 1200:
            return MarketStatus.AFTER_HOURS
        return MarketStatus.CLOSED

    def is_market_open(self) -> bool:
        return self.get_market_status() == MarketStatus.OPEN

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate(self, symbol: Optional[str] = None) -> None:
        """Invalidate cache for *symbol*, or everything if None."""
        if symbol:
            sym = symbol.upper()
            for prefix in (
                "quote", "company", "news", "earnings",
                "dividends", "financials", "analysts", "insider", "crypto",
            ):
                self._cache.delete(f"{prefix}:{sym}")
            self._cache.delete_prefix(f"hist:{sym}:")
            self._cache.delete_prefix(f"quotes:")
        else:
            self._cache.clear()

    def cache_size(self) -> int:
        return self._cache.size()
