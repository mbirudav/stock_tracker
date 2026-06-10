"""
Massive API Interface

Concrete provider implementations for Yahoo Finance, Alpha Vantage, Polygon.io,
and Finnhub. Also exposes MassiveAPIInterface — a pre-wired UnifiedMarketData
instance that aggregates all enabled providers with rate limiting and retries.
"""
from __future__ import annotations

import hashlib
import time
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from .config import Config, get_config
from .models import (
    Analyst,
    CompanyInfo,
    CryptoQuote,
    DataProvider,
    Dividend,
    Earnings,
    FinancialStatement,
    ForexRate,
    InsiderTransaction,
    Interval,
    MarketIndex,
    MarketMover,
    NewsItem,
    OHLCV,
    OptionChain,
    OptionContract,
    Period,
    Quote,
    SectorPerformance,
    TechnicalIndicator,
)
from .unified_market_data import MarketDataProvider, UnifiedMarketData


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Token-bucket rate limiter (per minute)."""

    def __init__(self, calls_per_minute: int) -> None:
        self._interval = 60.0 / max(calls_per_minute, 1)
        self._next_call = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._next_call - now
            if wait > 0:
                time.sleep(wait)
            self._next_call = time.monotonic() + self._interval


def _retry(fn, max_retries: int = 3, backoff: float = 1.0):
    """Retry *fn* up to *max_retries* times with exponential backoff."""
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(backoff * (2 ** attempt))
    raise last_exc


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ts(epoch: Optional[float]) -> Optional[datetime]:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Yahoo Finance provider (uses yfinance library)
# ---------------------------------------------------------------------------

class YahooFinanceProvider(MarketDataProvider):
    """Wraps the yfinance library for Yahoo Finance data."""

    def __init__(self, cfg: Optional[Config] = None) -> None:
        self._cfg = cfg or get_config()
        self._limiter = _RateLimiter(self._cfg.yahoo.rate_limit_per_minute)
        # Import lazily so the module is importable even without yfinance installed
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError as exc:
            raise ImportError(
                "yfinance is required for YahooFinanceProvider: pip install yfinance"
            ) from exc

    @property
    def provider_id(self) -> DataProvider:
        return DataProvider.YAHOO_FINANCE

    def _ticker(self, symbol: str):
        self._limiter.acquire()
        return self._yf.Ticker(symbol)

    def get_quote(self, symbol: str) -> Quote:
        def _fetch():
            t = self._ticker(symbol)
            info = t.info
            price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"), 0.0)
            prev = _safe_float(info.get("previousClose") or info.get("regularMarketPreviousClose"), price)
            change = price - prev
            change_pct = (change / prev * 100) if prev else 0.0
            return Quote(
                symbol=symbol.upper(),
                price=price,
                open=_safe_float(info.get("open") or info.get("regularMarketOpen"), price),
                high=_safe_float(info.get("dayHigh") or info.get("regularMarketDayHigh"), price),
                low=_safe_float(info.get("dayLow") or info.get("regularMarketDayLow"), price),
                close=price,
                prev_close=prev,
                volume=_safe_int(info.get("volume") or info.get("regularMarketVolume"), 0),
                timestamp=datetime.now(tz=timezone.utc),
                provider=DataProvider.YAHOO_FINANCE,
                change=change,
                change_percent=change_pct,
                bid=_safe_float(info.get("bid")),
                ask=_safe_float(info.get("ask")),
                bid_size=_safe_int(info.get("bidSize")),
                ask_size=_safe_int(info.get("askSize")),
                market_cap=_safe_float(info.get("marketCap")),
                pe_ratio=_safe_float(info.get("trailingPE")),
                dividend_yield=_safe_float(info.get("dividendYield")),
                fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
                fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
                average_volume=_safe_int(info.get("averageVolume")),
                shares_outstanding=_safe_float(info.get("sharesOutstanding")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        result: Dict[str, Quote] = {}
        for sym in symbols:
            try:
                result[sym.upper()] = self.get_quote(sym)
            except Exception:
                pass
        return result

    def get_historical(
        self,
        symbol: str,
        period: Period = Period.MONTH_1,
        interval: Interval = Interval.DAY_1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[OHLCV]:
        def _fetch():
            self._limiter.acquire()
            t = self._yf.Ticker(symbol)
            kwargs: Dict[str, Any] = {"interval": interval.value, "auto_adjust": True}
            if start or end:
                if start:
                    kwargs["start"] = start.strftime("%Y-%m-%d")
                if end:
                    kwargs["end"] = end.strftime("%Y-%m-%d")
            else:
                kwargs["period"] = period.value
            df = t.history(**kwargs)
            bars = []
            for ts, row in df.iterrows():
                bars.append(OHLCV(
                    symbol=symbol.upper(),
                    timestamp=ts.to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                    dividends=float(row.get("Dividends", 0)),
                    stock_splits=float(row.get("Stock Splits", 0)),
                ))
            return bars
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_company_info(self, symbol: str) -> CompanyInfo:
        def _fetch():
            t = self._ticker(symbol)
            info = t.info
            return CompanyInfo(
                symbol=symbol.upper(),
                name=info.get("longName") or info.get("shortName", symbol),
                sector=info.get("sector", "Unknown"),
                industry=info.get("industry", "Unknown"),
                description=info.get("longBusinessSummary", ""),
                employees=_safe_int(info.get("fullTimeEmployees")),
                website=info.get("website"),
                exchange=info.get("exchange"),
                currency=info.get("currency", "USD"),
                country=info.get("country"),
                market_cap=_safe_float(info.get("marketCap")),
                shares_outstanding=_safe_float(info.get("sharesOutstanding")),
                float_shares=_safe_float(info.get("floatShares")),
                beta=_safe_float(info.get("beta")),
                forward_pe=_safe_float(info.get("forwardPE")),
                trailing_pe=_safe_float(info.get("trailingPE")),
                price_to_book=_safe_float(info.get("priceToBook")),
                profit_margins=_safe_float(info.get("profitMargins")),
                revenue_growth=_safe_float(info.get("revenueGrowth")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_news(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        def _fetch():
            t = self._ticker(symbol)
            items = []
            for article in (t.news or [])[:limit]:
                items.append(NewsItem(
                    id=article.get("uuid", hashlib.md5(article.get("link", "").encode()).hexdigest()),
                    headline=article.get("title", ""),
                    summary=article.get("summary", ""),
                    url=article.get("link", ""),
                    source=article.get("publisher", ""),
                    timestamp=_ts(article.get("providerPublishTime")) or datetime.now(tz=timezone.utc),
                    symbols=[symbol.upper()] + article.get("relatedTickers", []),
                ))
            return items
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_dividends(self, symbol: str) -> List[Dividend]:
        def _fetch():
            self._limiter.acquire()
            t = self._yf.Ticker(symbol)
            divs = t.dividends
            result = []
            for ts, amount in divs.items():
                result.append(Dividend(
                    symbol=symbol.upper(),
                    amount=float(amount),
                    ex_date=ts.to_pydatetime(),
                    pay_date=ts.to_pydatetime(),
                    frequency="quarterly",
                    dividend_type="Cash",
                ))
            return result
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_earnings(self, symbol: str, quarters: int = 4) -> List[Earnings]:
        def _fetch():
            t = self._ticker(symbol)
            df = t.quarterly_earnings
            result = []
            if df is None or df.empty:
                return result
            for i, (period, row) in enumerate(df.iterrows()):
                if i >= quarters:
                    break
                result.append(Earnings(
                    symbol=symbol.upper(),
                    period=str(period),
                    report_date=datetime.now(tz=timezone.utc),
                    fiscal_year=datetime.now().year,
                    fiscal_quarter=4 - i,
                    eps_estimate=_safe_float(row.get("Estimate")),
                    eps_actual=_safe_float(row.get("Reported")),
                    surprise_percent=_safe_float(row.get("Surprise(%)")),
                ))
            return result
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_financials(self, symbol: str, period: str = "annual") -> List[FinancialStatement]:
        def _fetch():
            t = self._ticker(symbol)
            df = t.financials if period == "annual" else t.quarterly_financials
            result = []
            if df is None or df.empty:
                return result
            for col in df.columns:
                def _g(key: str) -> Optional[float]:
                    return _safe_float(df.loc[key, col]) if key in df.index else None
                result.append(FinancialStatement(
                    symbol=symbol.upper(),
                    period=period,
                    end_date=col.to_pydatetime() if hasattr(col, "to_pydatetime") else datetime.now(tz=timezone.utc),
                    revenue=_g("Total Revenue"),
                    gross_profit=_g("Gross Profit"),
                    operating_income=_g("Operating Income"),
                    net_income=_g("Net Income"),
                    ebitda=_g("EBITDA"),
                ))
            return result
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_options(self, symbol: str, expiry: Optional[datetime] = None) -> List[OptionChain]:
        def _fetch():
            self._limiter.acquire()
            t = self._yf.Ticker(symbol)
            expiry_dates = t.options
            if not expiry_dates:
                return []
            chains = []
            dates_to_fetch = [expiry_dates[0]] if expiry is None else [
                d for d in expiry_dates
                if abs((datetime.strptime(d, "%Y-%m-%d") - expiry).days) < 7
            ] or [expiry_dates[0]]

            for date_str in dates_to_fetch[:3]:
                chain_data = t.option_chain(date_str)
                expiry_dt = datetime.strptime(date_str, "%Y-%m-%d")
                calls = _parse_option_df(chain_data.calls, symbol, expiry_dt, "call")
                puts = _parse_option_df(chain_data.puts, symbol, expiry_dt, "put")
                chains.append(OptionChain(symbol=symbol.upper(), expiry=expiry_dt, calls=calls, puts=puts))
            return chains
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_market_indices(self) -> List[MarketIndex]:
        indices = {
            "^GSPC": "S&P 500", "^DJI": "Dow Jones", "^IXIC": "NASDAQ",
            "^RUT": "Russell 2000", "^VIX": "VIX", "^FTSE": "FTSE 100",
            "^N225": "Nikkei 225", "^HSI": "Hang Seng",
        }
        result = []
        for sym, name in indices.items():
            try:
                q = self.get_quote(sym)
                result.append(MarketIndex(
                    symbol=sym, name=name,
                    price=q.price, change=q.change, change_percent=q.change_percent,
                    timestamp=q.timestamp, open=q.open, high=q.high, low=q.low,
                    prev_close=q.prev_close, volume=q.volume,
                ))
            except Exception:
                pass
        return result

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        # yfinance doesn't have a search endpoint; return a best-guess ticker match
        try:
            self._limiter.acquire()
            t = self._yf.Ticker(query)
            info = t.info
            if info.get("symbol"):
                return [{"symbol": info["symbol"], "name": info.get("longName", ""), "type": info.get("quoteType", "")}]
        except Exception:
            pass
        return []


def _parse_option_df(df, underlying: str, expiry: datetime, opt_type: str) -> List[OptionContract]:
    contracts = []
    for _, row in df.iterrows():
        contracts.append(OptionContract(
            symbol=str(row.get("contractSymbol", "")),
            underlying=underlying.upper(),
            expiry=expiry,
            strike=_safe_float(row.get("strike"), 0.0),
            option_type=opt_type,
            bid=_safe_float(row.get("bid"), 0.0),
            ask=_safe_float(row.get("ask"), 0.0),
            last=_safe_float(row.get("lastPrice"), 0.0),
            volume=_safe_int(row.get("volume"), 0),
            open_interest=_safe_int(row.get("openInterest"), 0),
            implied_volatility=_safe_float(row.get("impliedVolatility")),
            in_the_money=bool(row.get("inTheMoney", False)),
            percent_change=_safe_float(row.get("percentChange")),
        ))
    return contracts


# ---------------------------------------------------------------------------
# Alpha Vantage provider
# ---------------------------------------------------------------------------

class AlphaVantageProvider(MarketDataProvider):
    """Alpha Vantage REST API provider."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, cfg: Optional[Config] = None) -> None:
        self._cfg = cfg or get_config()
        self._api_key = self._cfg.alpha_vantage.api_key
        self._limiter = _RateLimiter(self._cfg.alpha_vantage.rate_limit_per_minute)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "stock-tracker/1.0"

    @property
    def provider_id(self) -> DataProvider:
        return DataProvider.ALPHA_VANTAGE

    def _get(self, params: Dict[str, str]) -> Dict:
        self._limiter.acquire()
        params["apikey"] = self._api_key
        resp = self._session.get(self.BASE_URL, params=params, timeout=self._cfg.alpha_vantage.timeout)
        resp.raise_for_status()
        data = resp.json()
        if "Error Message" in data:
            raise ValueError(data["Error Message"])
        if "Note" in data:
            raise RuntimeError(f"Alpha Vantage rate limit: {data['Note']}")
        return data

    def get_quote(self, symbol: str) -> Quote:
        def _fetch():
            data = self._get({"function": "GLOBAL_QUOTE", "symbol": symbol})
            q = data.get("Global Quote", {})
            price = _safe_float(q.get("05. price"), 0.0)
            prev = _safe_float(q.get("08. previous close"), price)
            change = _safe_float(q.get("09. change"), 0.0)
            change_pct = _safe_float(q.get("10. change percent", "0%").replace("%", ""), 0.0)
            return Quote(
                symbol=symbol.upper(),
                price=price,
                open=_safe_float(q.get("02. open"), price),
                high=_safe_float(q.get("03. high"), price),
                low=_safe_float(q.get("04. low"), price),
                close=price,
                prev_close=prev,
                volume=_safe_int(q.get("06. volume"), 0),
                timestamp=datetime.now(tz=timezone.utc),
                provider=DataProvider.ALPHA_VANTAGE,
                change=change,
                change_percent=change_pct,
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        result: Dict[str, Quote] = {}
        for sym in symbols:
            try:
                result[sym.upper()] = self.get_quote(sym)
            except Exception:
                pass
        return result

    def get_historical(
        self,
        symbol: str,
        period: Period = Period.MONTH_1,
        interval: Interval = Interval.DAY_1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[OHLCV]:
        # Map interval to Alpha Vantage function
        intraday_map = {
            Interval.MINUTE_1: "1min", Interval.MINUTE_5: "5min",
            Interval.MINUTE_15: "15min", Interval.MINUTE_30: "30min",
            Interval.HOUR_1: "60min",
        }
        if interval in intraday_map:
            function = "TIME_SERIES_INTRADAY"
            params = {
                "function": function, "symbol": symbol,
                "interval": intraday_map[interval], "outputsize": "full",
                "datatype": "json",
            }
            key = f"Time Series ({intraday_map[interval]})"
        elif interval == Interval.WEEK_1:
            params = {"function": "TIME_SERIES_WEEKLY_ADJUSTED", "symbol": symbol, "datatype": "json"}
            key = "Weekly Adjusted Time Series"
        elif interval == Interval.MONTH_1:
            params = {"function": "TIME_SERIES_MONTHLY_ADJUSTED", "symbol": symbol, "datatype": "json"}
            key = "Monthly Adjusted Time Series"
        else:
            outputsize = "full" if period in (Period.YEAR_1, Period.YEAR_2, Period.YEAR_5, Period.YEAR_10, Period.MAX) else "compact"
            params = {"function": "TIME_SERIES_DAILY_ADJUSTED", "symbol": symbol, "outputsize": outputsize, "datatype": "json"}
            key = "Time Series (Daily)"

        def _fetch():
            data = self._get(params)
            ts_data = data.get(key, {})
            bars = []
            for date_str, values in sorted(ts_data.items()):
                try:
                    ts = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                bars.append(OHLCV(
                    symbol=symbol.upper(),
                    timestamp=ts,
                    open=_safe_float(values.get("1. open"), 0.0),
                    high=_safe_float(values.get("2. high"), 0.0),
                    low=_safe_float(values.get("3. low"), 0.0),
                    close=_safe_float(values.get("4. close") or values.get("5. adjusted close"), 0.0),
                    volume=_safe_int(values.get("6. volume") or values.get("5. volume"), 0),
                    adjusted_close=_safe_float(values.get("5. adjusted close")),
                ))
            return bars
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_company_info(self, symbol: str) -> CompanyInfo:
        def _fetch():
            data = self._get({"function": "OVERVIEW", "symbol": symbol})
            return CompanyInfo(
                symbol=symbol.upper(),
                name=data.get("Name", symbol),
                sector=data.get("Sector", "Unknown"),
                industry=data.get("Industry", "Unknown"),
                description=data.get("Description", ""),
                employees=_safe_int(data.get("FullTimeEmployees")),
                website=data.get("OfficialSite"),
                exchange=data.get("Exchange"),
                currency=data.get("Currency", "USD"),
                country=data.get("Country"),
                ipo_date=data.get("IPODate"),
                market_cap=_safe_float(data.get("MarketCapitalization")),
                shares_outstanding=_safe_float(data.get("SharesOutstanding")),
                beta=_safe_float(data.get("Beta")),
                forward_pe=_safe_float(data.get("ForwardPE")),
                trailing_pe=_safe_float(data.get("TrailingPE")),
                price_to_book=_safe_float(data.get("PriceToBookRatio")),
                profit_margins=_safe_float(data.get("ProfitMargin")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_news(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        def _fetch():
            data = self._get({
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "limit": str(min(limit, 50)),
            })
            items = []
            for article in data.get("feed", [])[:limit]:
                items.append(NewsItem(
                    id=hashlib.md5(article.get("url", "").encode()).hexdigest(),
                    headline=article.get("title", ""),
                    summary=article.get("summary", ""),
                    url=article.get("url", ""),
                    source=article.get("source", ""),
                    timestamp=_parse_av_datetime(article.get("time_published", "")),
                    symbols=[t["ticker"] for t in article.get("ticker_sentiment", [])],
                    sentiment=_safe_float(article.get("overall_sentiment_score")),
                    category=article.get("category_within_source"),
                    image_url=article.get("banner_image"),
                ))
            return items
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        interval: Interval = Interval.DAY_1,
    ) -> List[TechnicalIndicator]:
        interval_map = {
            Interval.MINUTE_1: "1min", Interval.MINUTE_5: "5min",
            Interval.MINUTE_15: "15min", Interval.MINUTE_30: "30min",
            Interval.HOUR_1: "60min", Interval.DAY_1: "daily",
            Interval.WEEK_1: "weekly", Interval.MONTH_1: "monthly",
        }
        av_interval = interval_map.get(interval, "daily")
        results = []
        for indicator in indicators:
            try:
                data = self._get({
                    "function": indicator.upper(),
                    "symbol": symbol,
                    "interval": av_interval,
                    "time_period": "14",
                    "series_type": "close",
                })
                key = f"Technical Analysis: {indicator.upper()}"
                series = data.get(key, {})
                for date_str, values in list(sorted(series.items()))[-1:]:
                    ts = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    results.append(TechnicalIndicator(
                        symbol=symbol.upper(),
                        indicator=indicator.upper(),
                        timestamp=ts,
                        values={k: _safe_float(v, 0.0) for k, v in values.items()},
                    ))
            except Exception:
                pass
        return results

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        def _fetch():
            data = self._get({"function": "SYMBOL_SEARCH", "keywords": query})
            results = []
            for match in data.get("bestMatches", [])[:limit]:
                results.append({
                    "symbol": match.get("1. symbol", ""),
                    "name": match.get("2. name", ""),
                    "type": match.get("3. type", ""),
                    "region": match.get("4. region", ""),
                    "currency": match.get("8. currency", ""),
                })
            return results
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_forex_rate(self, base: str, quote: str) -> ForexRate:
        def _fetch():
            data = self._get({
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": base.upper(),
                "to_currency": quote.upper(),
            })
            r = data.get("Realtime Currency Exchange Rate", {})
            rate = _safe_float(r.get("5. Exchange Rate"), 1.0)
            return ForexRate(
                base_currency=base.upper(),
                quote_currency=quote.upper(),
                rate=rate,
                bid=_safe_float(r.get("8. Bid Price"), rate),
                ask=_safe_float(r.get("9. Ask Price"), rate),
                timestamp=_parse_av_datetime(r.get("6. Last Refreshed", "")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_crypto_quote(self, symbol: str) -> CryptoQuote:
        def _fetch():
            data = self._get({
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": symbol.upper(),
                "to_currency": "USD",
            })
            r = data.get("Realtime Currency Exchange Rate", {})
            price = _safe_float(r.get("5. Exchange Rate"), 0.0)
            return CryptoQuote(
                symbol=symbol.upper(),
                name=r.get("1. From_Currency Name", symbol),
                price_usd=price,
                market_cap_usd=0.0,
                volume_24h_usd=0.0,
                change_24h=0.0,
                change_percent_24h=0.0,
                timestamp=_parse_av_datetime(r.get("6. Last Refreshed", "")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)


def _parse_av_datetime(s: str) -> datetime:
    for fmt in ("%Y%m%dT%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt.replace("%Y", "YYYY").replace("%m", "MM")
                                       .replace("%d", "DD").replace("%H", "HH")
                                       .replace("%M", "MM2").replace("%S", "SS"))], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Polygon.io provider
# ---------------------------------------------------------------------------

class PolygonProvider(MarketDataProvider):
    """Polygon.io REST API provider."""

    BASE_URL = "https://api.polygon.io"

    def __init__(self, cfg: Optional[Config] = None) -> None:
        self._cfg = cfg or get_config()
        self._api_key = self._cfg.polygon.api_key
        self._limiter = _RateLimiter(self._cfg.polygon.rate_limit_per_minute)
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": "stock-tracker/1.0",
        })

    @property
    def provider_id(self) -> DataProvider:
        return DataProvider.POLYGON

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        self._limiter.acquire()
        url = f"{self.BASE_URL}{path}"
        resp = self._session.get(url, params=params or {}, timeout=self._cfg.polygon.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_quote(self, symbol: str) -> Quote:
        def _fetch():
            snap = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.upper()}")
            t = snap.get("ticker", {})
            day = t.get("day", {})
            prev_day = t.get("prevDay", {})
            last_trade = t.get("lastTrade", {})
            last_quote = t.get("lastQuote", {})
            price = _safe_float(last_trade.get("p") or day.get("c"), 0.0)
            prev_close = _safe_float(prev_day.get("c"), price)
            return Quote(
                symbol=symbol.upper(),
                price=price,
                open=_safe_float(day.get("o"), price),
                high=_safe_float(day.get("h"), price),
                low=_safe_float(day.get("l"), price),
                close=_safe_float(day.get("c"), price),
                prev_close=prev_close,
                volume=_safe_int(day.get("v"), 0),
                timestamp=datetime.now(tz=timezone.utc),
                provider=DataProvider.POLYGON,
                change=price - prev_close,
                change_percent=((price - prev_close) / prev_close * 100) if prev_close else 0.0,
                bid=_safe_float(last_quote.get("P")),
                ask=_safe_float(last_quote.get("p")),
                average_volume=_safe_int(day.get("av")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        def _fetch():
            syms = ",".join(s.upper() for s in symbols)
            data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers", {"tickers": syms})
            result: Dict[str, Quote] = {}
            for t in data.get("tickers", []):
                sym = t.get("ticker", "")
                day = t.get("day", {})
                prev_day = t.get("prevDay", {})
                last_trade = t.get("lastTrade", {})
                last_quote = t.get("lastQuote", {})
                price = _safe_float(last_trade.get("p") or day.get("c"), 0.0)
                prev = _safe_float(prev_day.get("c"), price)
                result[sym] = Quote(
                    symbol=sym, price=price,
                    open=_safe_float(day.get("o"), price),
                    high=_safe_float(day.get("h"), price),
                    low=_safe_float(day.get("l"), price),
                    close=_safe_float(day.get("c"), price),
                    prev_close=prev,
                    volume=_safe_int(day.get("v"), 0),
                    timestamp=datetime.now(tz=timezone.utc),
                    provider=DataProvider.POLYGON,
                    change=price - prev,
                    change_percent=((price - prev) / prev * 100) if prev else 0.0,
                    bid=_safe_float(last_quote.get("P")),
                    ask=_safe_float(last_quote.get("p")),
                )
            return result
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_historical(
        self,
        symbol: str,
        period: Period = Period.MONTH_1,
        interval: Interval = Interval.DAY_1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[OHLCV]:
        mult_span = {
            Interval.MINUTE_1: (1, "minute"), Interval.MINUTE_5: (5, "minute"),
            Interval.MINUTE_15: (15, "minute"), Interval.MINUTE_30: (30, "minute"),
            Interval.HOUR_1: (1, "hour"), Interval.DAY_1: (1, "day"),
            Interval.WEEK_1: (1, "week"), Interval.MONTH_1: (1, "month"),
        }
        multiplier, timespan = mult_span.get(interval, (1, "day"))

        if not start:
            period_days = {
                Period.DAY_1: 1, Period.WEEK_1: 5, Period.MONTH_1: 30,
                Period.MONTH_3: 90, Period.MONTH_6: 180, Period.YEAR_1: 365,
                Period.YEAR_2: 730, Period.YEAR_5: 1825, Period.YEAR_10: 3650,
            }
            days = period_days.get(period, 30)
            from datetime import timedelta
            start = datetime.now() - timedelta(days=days)
        if not end:
            end = datetime.now()

        def _fetch():
            data = self._get(
                f"/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{timespan}"
                f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}",
                {"adjusted": "true", "sort": "asc", "limit": "5000"},
            )
            bars = []
            for r in data.get("results", []):
                ts = datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc)
                bars.append(OHLCV(
                    symbol=symbol.upper(),
                    timestamp=ts,
                    open=float(r["o"]),
                    high=float(r["h"]),
                    low=float(r["l"]),
                    close=float(r["c"]),
                    volume=int(r["v"]),
                    adjusted_close=float(r.get("vw", r["c"])),
                ))
            return bars
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_company_info(self, symbol: str) -> CompanyInfo:
        def _fetch():
            data = self._get(f"/v3/reference/tickers/{symbol.upper()}")
            r = data.get("results", {})
            return CompanyInfo(
                symbol=symbol.upper(),
                name=r.get("name", symbol),
                sector=r.get("sic_description", "Unknown"),
                industry=r.get("sic_description", "Unknown"),
                description=r.get("description", ""),
                employees=_safe_int(r.get("total_employees")),
                website=r.get("homepage_url"),
                exchange=r.get("primary_exchange"),
                currency=r.get("currency_name", "USD"),
                country=r.get("locale", "").upper(),
                ipo_date=r.get("list_date"),
                shares_outstanding=_safe_float(r.get("share_class_shares_outstanding")),
                market_cap=_safe_float(r.get("market_cap")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_news(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        def _fetch():
            data = self._get(
                "/v2/reference/news",
                {"ticker": symbol.upper(), "limit": str(min(limit, 50)), "sort": "published_utc", "order": "desc"},
            )
            items = []
            for a in data.get("results", [])[:limit]:
                items.append(NewsItem(
                    id=a.get("id", hashlib.md5(a.get("article_url", "").encode()).hexdigest()),
                    headline=a.get("title", ""),
                    summary=a.get("description", ""),
                    url=a.get("article_url", ""),
                    source=a.get("publisher", {}).get("name", ""),
                    timestamp=_parse_polygon_ts(a.get("published_utc", "")),
                    symbols=a.get("tickers", []),
                    image_url=a.get("image_url"),
                ))
            return items
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_market_movers(self, category: str = "gainers", limit: int = 20) -> List[MarketMover]:
        def _fetch():
            direction = "gainers" if category in ("gainers", "gainer") else "losers"
            data = self._get(f"/v2/snapshot/locale/us/markets/stocks/{direction}")
            movers = []
            for t in data.get("tickers", [])[:limit]:
                day = t.get("day", {})
                prev = t.get("prevDay", {})
                price = _safe_float(day.get("c"), 0.0)
                prev_c = _safe_float(prev.get("c"), price)
                movers.append(MarketMover(
                    symbol=t.get("ticker", ""),
                    name=t.get("ticker", ""),
                    price=price,
                    change=price - prev_c,
                    change_percent=t.get("todaysChangePerc", 0.0),
                    volume=_safe_int(day.get("v"), 0),
                ))
            return movers
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        def _fetch():
            data = self._get(
                "/v3/reference/tickers",
                {"search": query, "limit": str(limit), "active": "true"},
            )
            return [
                {"symbol": r["ticker"], "name": r.get("name", ""), "type": r.get("type", ""), "exchange": r.get("primary_exchange", "")}
                for r in data.get("results", [])
            ]
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)


def _parse_polygon_ts(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt)+2], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Finnhub provider
# ---------------------------------------------------------------------------

class FinnhubProvider(MarketDataProvider):
    """Finnhub.io REST API provider."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, cfg: Optional[Config] = None) -> None:
        self._cfg = cfg or get_config()
        self._api_key = self._cfg.finnhub.api_key
        self._limiter = _RateLimiter(self._cfg.finnhub.rate_limit_per_minute)
        self._session = requests.Session()
        self._session.headers.update({"X-Finnhub-Token": self._api_key, "User-Agent": "stock-tracker/1.0"})

    @property
    def provider_id(self) -> DataProvider:
        return DataProvider.FINNHUB

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        self._limiter.acquire()
        resp = self._session.get(
            f"{self.BASE_URL}{path}",
            params=params or {},
            timeout=self._cfg.finnhub.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_quote(self, symbol: str) -> Quote:
        def _fetch():
            q = self._get("/quote", {"symbol": symbol.upper()})
            price = _safe_float(q.get("c"), 0.0)
            prev = _safe_float(q.get("pc"), price)
            return Quote(
                symbol=symbol.upper(),
                price=price,
                open=_safe_float(q.get("o"), price),
                high=_safe_float(q.get("h"), price),
                low=_safe_float(q.get("l"), price),
                close=price,
                prev_close=prev,
                volume=0,
                timestamp=_ts(q.get("t")) or datetime.now(tz=timezone.utc),
                provider=DataProvider.FINNHUB,
                change=_safe_float(q.get("d"), 0.0),
                change_percent=_safe_float(q.get("dp"), 0.0),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        result: Dict[str, Quote] = {}
        for sym in symbols:
            try:
                result[sym.upper()] = self.get_quote(sym)
            except Exception:
                pass
        return result

    def get_historical(
        self,
        symbol: str,
        period: Period = Period.MONTH_1,
        interval: Interval = Interval.DAY_1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[OHLCV]:
        res_map = {
            Interval.MINUTE_1: "1", Interval.MINUTE_5: "5", Interval.MINUTE_15: "15",
            Interval.MINUTE_30: "30", Interval.HOUR_1: "60",
            Interval.DAY_1: "D", Interval.WEEK_1: "W", Interval.MONTH_1: "M",
        }
        resolution = res_map.get(interval, "D")

        if not start:
            from datetime import timedelta
            period_days = {
                Period.DAY_1: 1, Period.WEEK_1: 7, Period.MONTH_1: 30,
                Period.MONTH_3: 90, Period.MONTH_6: 180, Period.YEAR_1: 365,
                Period.YEAR_2: 730, Period.YEAR_5: 1825, Period.YEAR_10: 3650,
            }
            start = datetime.now() - timedelta(days=period_days.get(period, 30))
        if not end:
            end = datetime.now()

        def _fetch():
            data = self._get("/stock/candle", {
                "symbol": symbol.upper(), "resolution": resolution,
                "from": str(int(start.timestamp())), "to": str(int(end.timestamp())),
            })
            if data.get("s") == "no_data":
                return []
            bars = []
            for i in range(len(data.get("t", []))):
                bars.append(OHLCV(
                    symbol=symbol.upper(),
                    timestamp=_ts(data["t"][i]) or datetime.now(tz=timezone.utc),
                    open=float(data["o"][i]),
                    high=float(data["h"][i]),
                    low=float(data["l"][i]),
                    close=float(data["c"][i]),
                    volume=int(data["v"][i]),
                ))
            return bars
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_company_info(self, symbol: str) -> CompanyInfo:
        def _fetch():
            profile = self._get("/stock/profile2", {"symbol": symbol.upper()})
            return CompanyInfo(
                symbol=symbol.upper(),
                name=profile.get("name", symbol),
                sector=profile.get("finnhubIndustry", "Unknown"),
                industry=profile.get("finnhubIndustry", "Unknown"),
                description="",
                employees=_safe_int(profile.get("employeeTotal")),
                website=profile.get("weburl"),
                exchange=profile.get("exchange"),
                currency=profile.get("currency", "USD"),
                country=profile.get("country"),
                ipo_date=profile.get("ipo"),
                market_cap=_safe_float(profile.get("marketCapitalization")),
                shares_outstanding=_safe_float(profile.get("shareOutstanding")),
            )
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_news(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        from datetime import timedelta
        def _fetch():
            end = datetime.now()
            start = end - timedelta(days=7)
            articles = self._get("/company-news", {
                "symbol": symbol.upper(),
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
            })
            items = []
            for a in articles[:limit]:
                items.append(NewsItem(
                    id=str(a.get("id", hashlib.md5(a.get("url", "").encode()).hexdigest())),
                    headline=a.get("headline", ""),
                    summary=a.get("summary", ""),
                    url=a.get("url", ""),
                    source=a.get("source", ""),
                    timestamp=_ts(a.get("datetime")) or datetime.now(tz=timezone.utc),
                    symbols=[symbol.upper()],
                    sentiment=a.get("sentiment"),
                    category=a.get("category"),
                    image_url=a.get("image"),
                ))
            return items
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_analyst_ratings(self, symbol: str) -> List[Analyst]:
        def _fetch():
            data = self._get("/stock/recommendation", {"symbol": symbol.upper()})
            results = []
            for rec in data:
                total = sum([
                    rec.get("strongBuy", 0), rec.get("buy", 0),
                    rec.get("hold", 0), rec.get("sell", 0), rec.get("strongSell", 0),
                ])
                dominant = max(
                    ("Strong Buy", rec.get("strongBuy", 0)),
                    ("Buy", rec.get("buy", 0)),
                    ("Hold", rec.get("hold", 0)),
                    ("Sell", rec.get("sell", 0)),
                    ("Strong Sell", rec.get("strongSell", 0)),
                    key=lambda x: x[1],
                )[0]
                results.append(Analyst(
                    symbol=symbol.upper(),
                    firm="Consensus",
                    analyst=None,
                    rating=dominant,
                    target_price=None,
                    date=datetime.strptime(rec.get("period", "2000-01-01"), "%Y-%m-%d").replace(tzinfo=timezone.utc),
                ))
            return results
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_earnings(self, symbol: str, quarters: int = 4) -> List[Earnings]:
        def _fetch():
            data = self._get("/stock/earnings", {"symbol": symbol.upper(), "limit": str(quarters)})
            results = []
            for e in data[:quarters]:
                results.append(Earnings(
                    symbol=symbol.upper(),
                    period=e.get("period", ""),
                    report_date=datetime.strptime(e.get("period", "2000-01-01"), "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    fiscal_year=int(e.get("period", "2000-01-01")[:4]),
                    fiscal_quarter=1,
                    eps_estimate=_safe_float(e.get("estimate")),
                    eps_actual=_safe_float(e.get("actual")),
                    surprise_percent=_safe_float(e.get("surprisePercent")),
                ))
            return results
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_insider_transactions(self, symbol: str) -> List[InsiderTransaction]:
        def _fetch():
            data = self._get("/stock/insider-transactions", {"symbol": symbol.upper()})
            results = []
            for tx in data.get("data", []):
                txtype = "buy" if _safe_float(tx.get("change"), 0) > 0 else "sell"
                shares = abs(_safe_int(tx.get("change"), 0))
                price = _safe_float(tx.get("transactionPrice"), 0.0)
                results.append(InsiderTransaction(
                    symbol=symbol.upper(),
                    insider_name=tx.get("name", ""),
                    title="",
                    transaction_type=txtype,
                    shares=shares,
                    price=price,
                    value=shares * price,
                    transaction_date=datetime.strptime(tx.get("transactionDate", "2000-01-01"), "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    filing_date=datetime.strptime(tx.get("filingDate", "2000-01-01"), "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    shares_owned_after=_safe_int(tx.get("share")),
                ))
            return results
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        def _fetch():
            data = self._get("/search", {"q": query})
            return [
                {"symbol": r["symbol"], "name": r.get("description", ""), "type": r.get("type", "")}
                for r in data.get("result", [])[:limit]
            ]
        return _retry(_fetch, self._cfg.max_retries, self._cfg.retry_backoff)

    def get_market_indices(self) -> List[MarketIndex]:
        major = [("^GSPC", "S&P 500"), ("^DJI", "Dow Jones"), ("^IXIC", "NASDAQ"), ("^RUT", "Russell 2000")]
        indices = []
        for sym, name in major:
            try:
                q = self.get_quote(sym.replace("^", ""))
                indices.append(MarketIndex(
                    symbol=sym, name=name, price=q.price,
                    change=q.change, change_percent=q.change_percent,
                    timestamp=q.timestamp,
                ))
            except Exception:
                pass
        return indices


# ---------------------------------------------------------------------------
# MassiveAPIInterface — pre-wired aggregator
# ---------------------------------------------------------------------------

class MassiveAPIInterface(UnifiedMarketData):
    """
    Batteries-included market data interface.

    Automatically instantiates all available providers (based on which API keys
    are present in the environment / Config) and registers them in priority order:
    Yahoo Finance → Alpha Vantage → Polygon → Finnhub.

    Yahoo Finance is always enabled (no API key needed).
    """

    def __init__(self, cfg: Optional[Config] = None) -> None:
        super().__init__()
        self._cfg = cfg or get_config()
        self._register_providers()

    def _register_providers(self) -> None:
        # Yahoo Finance — always available
        try:
            yahoo = YahooFinanceProvider(self._cfg)
            self.add_provider(yahoo, primary=True)
        except ImportError:
            pass

        # Alpha Vantage — if key configured
        if self._cfg.alpha_vantage.api_key and self._cfg.alpha_vantage.enabled:
            try:
                self.add_provider(AlphaVantageProvider(self._cfg))
            except Exception:
                pass

        # Polygon — if key configured
        if self._cfg.polygon.api_key and self._cfg.polygon.enabled:
            try:
                self.add_provider(PolygonProvider(self._cfg))
            except Exception:
                pass

        # Finnhub — if key configured
        if self._cfg.finnhub.api_key and self._cfg.finnhub.enabled:
            try:
                self.add_provider(FinnhubProvider(self._cfg))
            except Exception:
                pass

    @property
    def active_providers(self) -> List[DataProvider]:
        return [p.provider_id for p in self._registry.all_ordered()]
