"""
Market Data Simulator

A self-contained implementation of MarketDataProvider that generates
realistic synthetic market data — no external API calls required.

Useful for:
- Development and testing without API keys
- Offline / CI environments
- Stress-testing the application with controlled data
- Demonstrations

Price dynamics:
- Geometric Brownian Motion (GBM) for price series
- Mean-reversion (Ornstein–Uhlenbeck) overlay for intraday behaviour
- Configurable volatility, drift, and jump diffusion
- Realistic bid-ask spreads and volume profiles
"""
from __future__ import annotations

import hashlib
import math
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

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
    MarketStatus,
    NewsItem,
    OHLCV,
    OptionChain,
    OptionContract,
    Period,
    Quote,
    SectorPerformance,
    TechnicalIndicator,
)
from .unified_market_data import MarketDataProvider


# ---------------------------------------------------------------------------
# Preloaded universe of simulated tickers
# ---------------------------------------------------------------------------

_TICKER_UNIVERSE: Dict[str, Tuple[str, str, str, float]] = {
    # symbol: (name, sector, industry, baseline_price)
    "AAPL":  ("Apple Inc.",                "Technology",           "Consumer Electronics",      185.0),
    "MSFT":  ("Microsoft Corporation",     "Technology",           "Software—Infrastructure",   415.0),
    "GOOGL": ("Alphabet Inc.",             "Technology",           "Internet Content & Info",   175.0),
    "AMZN":  ("Amazon.com Inc.",           "Consumer Cyclical",    "Internet Retail",           185.0),
    "NVDA":  ("NVIDIA Corporation",        "Technology",           "Semiconductors",            875.0),
    "META":  ("Meta Platforms Inc.",       "Technology",           "Internet Content & Info",   510.0),
    "TSLA":  ("Tesla Inc.",                "Consumer Cyclical",    "Auto Manufacturers",        175.0),
    "AVGO":  ("Broadcom Inc.",             "Technology",           "Semiconductors",            170.0),
    "LLY":   ("Eli Lilly and Company",     "Healthcare",           "Drug Manufacturers",        800.0),
    "JPM":   ("JPMorgan Chase & Co.",      "Financial Services",   "Banks—Diversified",         200.0),
    "V":     ("Visa Inc.",                 "Financial Services",   "Credit Services",           275.0),
    "UNH":   ("UnitedHealth Group Inc.",   "Healthcare",           "Healthcare Plans",          520.0),
    "XOM":   ("Exxon Mobil Corporation",   "Energy",               "Oil & Gas Integrated",       115.0),
    "MA":    ("Mastercard Incorporated",   "Financial Services",   "Credit Services",           455.0),
    "PG":    ("Procter & Gamble Co.",      "Consumer Defensive",   "Household & Personal Prod", 165.0),
    "JNJ":   ("Johnson & Johnson",         "Healthcare",           "Drug Manufacturers",        155.0),
    "HD":    ("The Home Depot Inc.",       "Consumer Cyclical",    "Home Improvement Retail",   360.0),
    "ABBV":  ("AbbVie Inc.",               "Healthcare",           "Drug Manufacturers",        175.0),
    "BAC":   ("Bank of America Corp.",     "Financial Services",   "Banks—Diversified",          38.0),
    "KO":    ("The Coca-Cola Company",     "Consumer Defensive",   "Beverages—Non-Alcoholic",    62.0),
    "WMT":   ("Walmart Inc.",              "Consumer Defensive",   "Discount Stores",            68.0),
    "CVX":   ("Chevron Corporation",       "Energy",               "Oil & Gas Integrated",       155.0),
    "MRK":   ("Merck & Co. Inc.",          "Healthcare",           "Drug Manufacturers",        130.0),
    "NFLX":  ("Netflix Inc.",              "Communication Svcs",   "Entertainment",             640.0),
    "AMD":   ("Advanced Micro Devices",    "Technology",           "Semiconductors",            165.0),
    "DIS":   ("The Walt Disney Company",   "Communication Svcs",   "Entertainment",              95.0),
    "INTC":  ("Intel Corporation",         "Technology",           "Semiconductors",             30.0),
    "CSCO":  ("Cisco Systems Inc.",        "Technology",           "Communication Equipment",    49.0),
    "CRM":   ("Salesforce Inc.",           "Technology",           "Software—Application",      285.0),
    "IBM":   ("IBM Corporation",           "Technology",           "Information Technology Svcs",195.0),
    # Indices (simulated)
    "^GSPC": ("S&P 500",                   "Index",                "Broad Market",             5000.0),
    "^DJI":  ("Dow Jones Industrial Avg",  "Index",                "Broad Market",            38000.0),
    "^IXIC": ("NASDAQ Composite",          "Index",                "Broad Market",            16000.0),
    "^RUT":  ("Russell 2000",              "Index",                "Small Cap",                2100.0),
    "^VIX":  ("CBOE Volatility Index",     "Index",                "Volatility",                  18.0),
    # Crypto
    "BTC":   ("Bitcoin",                   "Crypto",               "Cryptocurrency",           65000.0),
    "ETH":   ("Ethereum",                  "Crypto",               "Cryptocurrency",            3200.0),
    "SOL":   ("Solana",                    "Crypto",               "Cryptocurrency",             160.0),
}

_NEWS_TEMPLATES = [
    "{name} reports quarterly earnings, {beat_miss} analyst expectations",
    "{name} announces new product launch, shares {move}",
    "Analysts {upgrade_downgrade} {name} with price target of ${target}",
    "{name} CEO {action} in latest press conference",
    "SEC filing reveals insider {buy_sell} in {name}",
    "{name} stock {move} as market reacts to Fed announcement",
    "{name} acquires {target_company} in ${deal_size}B deal",
    "{sector} sector rallies; {name} among top {mover_type}",
    "{name} sets new {high_low} as trading volume surges",
    "Institutional investors {accumulate_trim} positions in {name}",
]

_SOURCES = ["Reuters", "Bloomberg", "MarketWatch", "CNBC", "Yahoo Finance",
            "The Wall Street Journal", "Financial Times", "Barron's"]

_ANALYST_FIRMS = [
    "Goldman Sachs", "Morgan Stanley", "JPMorgan", "Bank of America",
    "Citigroup", "UBS", "Barclays", "Deutsche Bank", "Wells Fargo",
    "Raymond James", "Piper Sandler", "Cowen", "Jefferies", "Needham",
]

_RATINGS = ["Strong Buy", "Buy", "Hold", "Underperform", "Sell"]

_SECTOR_LIST = [
    "Technology", "Healthcare", "Financial Services", "Consumer Cyclical",
    "Consumer Defensive", "Energy", "Industrials", "Communication Services",
    "Basic Materials", "Real Estate", "Utilities",
]


# ---------------------------------------------------------------------------
# Random walk helpers (deterministic per symbol+seed, reproducible)
# ---------------------------------------------------------------------------

class _PRNG:
    """Thread-safe, seedable pseudo-random number generator (LCG)."""

    def __init__(self, seed: int = 42) -> None:
        self._state = seed
        self._lock = threading.Lock()

    def seed(self, s: int) -> None:
        with self._lock:
            self._state = s

    def random(self) -> float:
        with self._lock:
            self._state = (self._state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
            return (self._state >> 33) / (2 ** 31)

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        # Box-Muller
        u1 = max(self.random(), 1e-10)
        u2 = self.random()
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        return mu + sigma * z

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()

    def choice(self, seq):
        return seq[int(self.random() * len(seq)) % len(seq)]

    def randint(self, a: int, b: int) -> int:
        return a + int(self.random() * (b - a + 1)) % (b - a + 1)


def _symbol_seed(symbol: str) -> int:
    return int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)


def _gbm_series(
    start_price: float,
    n: int,
    dt: float = 1 / 252,
    mu: float = 0.08,
    sigma: float = 0.20,
    prng: Optional[_PRNG] = None,
) -> List[float]:
    """Generate *n* prices via Geometric Brownian Motion."""
    if prng is None:
        prng = _PRNG()
    prices = [start_price]
    for _ in range(n - 1):
        z = prng.gauss(0, 1)
        price = prices[-1] * math.exp((mu - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * z)
        prices.append(max(price, 0.01))
    return prices


def _bar_from_price(
    symbol: str,
    ts: datetime,
    open_price: float,
    close_price: float,
    prng: _PRNG,
    volume_base: int = 1_000_000,
) -> OHLCV:
    """Construct a realistic OHLCV bar given open and close."""
    lo = min(open_price, close_price)
    hi = max(open_price, close_price)
    spread = hi - lo if hi != lo else open_price * 0.005
    high = hi + prng.uniform(0, spread * 0.5)
    low = lo - prng.uniform(0, spread * 0.5)
    volume = int(volume_base * prng.uniform(0.5, 2.0))
    return OHLCV(
        symbol=symbol.upper(),
        timestamp=ts,
        open=round(open_price, 4),
        high=round(high, 4),
        low=max(round(low, 4), 0.01),
        close=round(close_price, 4),
        volume=volume,
        adjusted_close=round(close_price, 4),
    )


def _bid_ask(price: float, prng: _PRNG) -> Tuple[float, float]:
    half_spread = price * prng.uniform(0.0002, 0.001)
    return round(price - half_spread, 4), round(price + half_spread, 4)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class MarketDataSimulator(MarketDataProvider):
    """
    Fully-featured simulated market data provider.

    All prices are generated deterministically from a seed so that results are
    reproducible.  The live-quote path advances prices as wall-clock time moves
    forward so the simulation feels "live" without requiring any network calls.
    """

    def __init__(
        self,
        seed: int = 42,
        annual_volatility: float = 0.25,
        annual_drift: float = 0.08,
        market_hours_only: bool = False,
    ) -> None:
        self._global_prng = _PRNG(seed)
        self._sigma = annual_volatility
        self._mu = annual_drift
        self._market_hours_only = market_hours_only
        # Per-symbol price state
        self._prices: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._last_tick: Dict[str, float] = {}  # monotonic time of last price update

    @property
    def provider_id(self) -> DataProvider:
        return DataProvider.SIMULATOR

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _baseline(self, symbol: str) -> float:
        sym = symbol.upper()
        if sym in _TICKER_UNIVERSE:
            return _TICKER_UNIVERSE[sym][3]
        # Derive a plausible price from the symbol string
        seed = _symbol_seed(sym)
        prng = _PRNG(seed)
        return round(prng.uniform(5.0, 500.0), 2)

    def _current_price(self, symbol: str) -> float:
        sym = symbol.upper()
        with self._lock:
            if sym not in self._prices:
                self._prices[sym] = self._baseline(sym)
                self._last_tick[sym] = time.monotonic()
                return self._prices[sym]

            # Advance price with GBM using elapsed real-time seconds
            elapsed = time.monotonic() - self._last_tick[sym]
            if elapsed < 0.5:
                return self._prices[sym]

            # Treat each elapsed second as a fraction of a trading day
            dt = elapsed / (6.5 * 3600)
            prng = _PRNG(_symbol_seed(sym) + int(time.monotonic() * 1000))
            z = prng.gauss(0, 1)
            factor = math.exp((self._mu - 0.5 * self._sigma ** 2) * dt + self._sigma * math.sqrt(dt) * z)
            # Rare jumps (~2% chance per tick)
            if prng.random() < 0.02:
                jump = prng.gauss(0, 0.03)
                factor *= math.exp(jump)
            self._prices[sym] = max(self._prices[sym] * factor, 0.01)
            self._last_tick[sym] = time.monotonic()
            return self._prices[sym]

    def _prev_close(self, symbol: str) -> float:
        prng = _PRNG(_symbol_seed(symbol) + 1)
        baseline = self._baseline(symbol)
        return round(baseline * prng.uniform(0.97, 1.03), 4)

    def _ticker_info(self, symbol: str) -> Tuple[str, str, str]:
        sym = symbol.upper()
        if sym in _TICKER_UNIVERSE:
            _, sector, industry, _ = _TICKER_UNIVERSE[sym]
            name = _TICKER_UNIVERSE[sym][0]
            return name, sector, industry
        prng = _PRNG(_symbol_seed(sym))
        sector = prng.choice(_SECTOR_LIST)
        return sym, sector, "General"

    # ------------------------------------------------------------------
    # Required API
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper()
        price = self._current_price(sym)
        prev = self._prev_close(sym)
        change = price - prev
        change_pct = (change / prev * 100) if prev else 0.0
        prng = _PRNG(_symbol_seed(sym) + int(time.time()))
        bid, ask = _bid_ask(price, prng)

        # Intraday open/high/low
        open_px = round(prev * prng.uniform(0.995, 1.005), 4)
        high_px = max(price, open_px) * prng.uniform(1.0, 1.015)
        low_px  = min(price, open_px) * prng.uniform(0.985, 1.0)
        vol_base = int(self._baseline(sym) * 10_000)
        volume   = int(vol_base * prng.uniform(0.5, 2.5))

        name, sector, industry = self._ticker_info(sym)
        return Quote(
            symbol=sym,
            price=round(price, 4),
            open=round(open_px, 4),
            high=round(high_px, 4),
            low=round(low_px, 4),
            close=round(price, 4),
            prev_close=prev,
            volume=volume,
            timestamp=datetime.now(tz=timezone.utc),
            provider=DataProvider.SIMULATOR,
            change=round(change, 4),
            change_percent=round(change_pct, 4),
            bid=bid,
            ask=ask,
            bid_size=prng.randint(100, 5000),
            ask_size=prng.randint(100, 5000),
            market_cap=round(price * prng.uniform(1e9, 3e12), 0),
            pe_ratio=round(prng.uniform(10, 50), 2),
            dividend_yield=round(prng.uniform(0, 0.04), 4),
            fifty_two_week_high=round(price * prng.uniform(1.0, 1.5), 4),
            fifty_two_week_low=round(price * prng.uniform(0.5, 1.0), 4),
            average_volume=int(vol_base * 1.2),
        )

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        return {sym.upper(): self.get_quote(sym) for sym in symbols}

    def get_historical(
        self,
        symbol: str,
        period: Period = Period.MONTH_1,
        interval: Interval = Interval.DAY_1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[OHLCV]:
        sym = symbol.upper()
        prng = _PRNG(_symbol_seed(sym))
        baseline = self._baseline(sym)

        if not end:
            end = datetime.now(tz=timezone.utc)
        if not start:
            period_td = {
                Period.DAY_1: timedelta(days=1),
                Period.WEEK_1: timedelta(weeks=1),
                Period.MONTH_1: timedelta(days=30),
                Period.MONTH_3: timedelta(days=90),
                Period.MONTH_6: timedelta(days=180),
                Period.YEAR_1: timedelta(days=365),
                Period.YEAR_2: timedelta(days=730),
                Period.YEAR_5: timedelta(days=1825),
                Period.YEAR_10: timedelta(days=3650),
                Period.MAX: timedelta(days=7300),
            }
            start = end - period_td.get(period, timedelta(days=30))

        # Determine bar frequency
        bar_td = {
            Interval.MINUTE_1: timedelta(minutes=1),
            Interval.MINUTE_5: timedelta(minutes=5),
            Interval.MINUTE_15: timedelta(minutes=15),
            Interval.MINUTE_30: timedelta(minutes=30),
            Interval.HOUR_1: timedelta(hours=1),
            Interval.DAY_1: timedelta(days=1),
            Interval.WEEK_1: timedelta(weeks=1),
            Interval.MONTH_1: timedelta(days=30),
        }
        step = bar_td.get(interval, timedelta(days=1))
        dt_fraction = step.total_seconds() / (252 * 6.5 * 3600)

        bars: List[OHLCV] = []
        ts = start
        price = baseline * prng.uniform(0.7, 1.3)
        vol_base = int(baseline * 10_000)

        while ts <= end:
            # Skip weekends for daily+ intervals
            if interval in (Interval.DAY_1, Interval.WEEK_1, Interval.MONTH_1):
                if ts.weekday() >= 5:
                    ts += step
                    continue

            z = prng.gauss(0, 1)
            next_price = price * math.exp(
                (self._mu - 0.5 * self._sigma ** 2) * dt_fraction
                + self._sigma * math.sqrt(dt_fraction) * z
            )
            next_price = max(next_price, 0.01)
            bar = _bar_from_price(sym, ts, price, next_price, prng, vol_base)
            bars.append(bar)
            price = next_price
            ts += step

        return bars

    def get_company_info(self, symbol: str) -> CompanyInfo:
        sym = symbol.upper()
        name, sector, industry = self._ticker_info(sym)
        prng = _PRNG(_symbol_seed(sym))
        price = self._baseline(sym)
        return CompanyInfo(
            symbol=sym,
            name=name,
            sector=sector,
            industry=industry,
            description=f"{name} is a simulated company in the {industry} industry.",
            employees=prng.randint(1_000, 250_000),
            website=f"https://www.{sym.lower()}.example.com",
            exchange="NASDAQ" if prng.random() > 0.4 else "NYSE",
            currency="USD",
            country="US",
            ipo_date=f"{prng.randint(1990, 2020)}-{prng.randint(1, 12):02d}-{prng.randint(1, 28):02d}",
            market_cap=round(price * prng.uniform(1e9, 3e12), 0),
            shares_outstanding=round(prng.uniform(1e8, 1e10), 0),
            float_shares=round(prng.uniform(5e7, 9e9), 0),
            beta=round(prng.uniform(0.5, 2.5), 2),
            forward_pe=round(prng.uniform(10, 50), 2),
            trailing_pe=round(prng.uniform(12, 60), 2),
            price_to_book=round(prng.uniform(1, 20), 2),
            profit_margins=round(prng.uniform(-0.05, 0.40), 4),
            revenue_growth=round(prng.uniform(-0.20, 0.50), 4),
        )

    def get_news(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        sym = symbol.upper()
        name, sector, _ = self._ticker_info(sym)
        prng = _PRNG(_symbol_seed(sym) + int(time.time() // 3600))
        items = []
        for i in range(min(limit, 20)):
            age = timedelta(hours=prng.uniform(0, 48 * (i + 1)))
            ts = datetime.now(tz=timezone.utc) - age
            headline = prng.choice([
                f"{name} reports quarterly earnings, {'beats' if prng.random() > 0.4 else 'misses'} analyst expectations",
                f"Analysts {'upgrade' if prng.random() > 0.5 else 'downgrade'} {name} with ${round(prng.uniform(50, 1000), 0):.0f} price target",
                f"{name} announces {'expansion' if prng.random() > 0.5 else 'restructuring'} plans",
                f"{sector} sector {'rallies' if prng.random() > 0.5 else 'declines'}; {name} among top movers",
                f"{name} insider {'buys' if prng.random() > 0.5 else 'sells'} ${round(prng.uniform(1, 50), 1):.1f}M in shares",
                f"{name} stock {'surges' if prng.random() > 0.5 else 'slides'} on {prng.choice(['earnings', 'macro data', 'sector news', 'guidance'])}",
                f"{name} sets new {'52-week high' if prng.random() > 0.5 else '52-week low'} amid {'strong' if prng.random() > 0.5 else 'weak'} volume",
            ])
            items.append(NewsItem(
                id=hashlib.md5(f"{sym}{i}{ts}".encode()).hexdigest(),
                headline=headline,
                summary=f"[Simulated] {headline}. The stock moved in response to market conditions.",
                url=f"https://news.example.com/{sym.lower()}-{i}",
                source=prng.choice(_SOURCES),
                timestamp=ts,
                symbols=[sym],
                sentiment=round(prng.uniform(-1.0, 1.0), 3),
                category="earnings" if "earnings" in headline.lower() else "general",
            ))
        return items

    # ------------------------------------------------------------------
    # Optional API
    # ------------------------------------------------------------------

    def get_options(self, symbol: str, expiry: Optional[datetime] = None) -> List[OptionChain]:
        sym = symbol.upper()
        price = self._current_price(sym)
        prng = _PRNG(_symbol_seed(sym))

        # Generate 3 expiry dates
        today = datetime.now(tz=timezone.utc)
        expiries = [today + timedelta(weeks=w) for w in (1, 4, 13)]
        if expiry:
            expiries = sorted(expiries, key=lambda e: abs((e - expiry).days))[:1]

        chains = []
        for exp in expiries[:3]:
            strikes = [round(price * f, 2) for f in (0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2)]
            calls, puts = [], []
            for strike in strikes:
                t = max((exp - today).days / 365, 0.0)
                sigma = 0.3
                bid_c, ask_c, delta_c = _bs_option(price, strike, t, 0.05, sigma, "call")
                bid_p, ask_p, delta_p = _bs_option(price, strike, t, 0.05, sigma, "put")
                oi = prng.randint(100, 10000)
                calls.append(OptionContract(
                    symbol=f"{sym}{exp.strftime('%y%m%d')}C{strike:.0f}",
                    underlying=sym, expiry=exp, strike=strike, option_type="call",
                    bid=bid_c, ask=ask_c, last=round((bid_c + ask_c) / 2, 2),
                    volume=prng.randint(0, 5000), open_interest=oi,
                    implied_volatility=round(sigma * prng.uniform(0.8, 1.3), 4),
                    delta=round(delta_c, 4),
                    in_the_money=price > strike,
                ))
                puts.append(OptionContract(
                    symbol=f"{sym}{exp.strftime('%y%m%d')}P{strike:.0f}",
                    underlying=sym, expiry=exp, strike=strike, option_type="put",
                    bid=bid_p, ask=ask_p, last=round((bid_p + ask_p) / 2, 2),
                    volume=prng.randint(0, 5000), open_interest=oi,
                    implied_volatility=round(sigma * prng.uniform(0.8, 1.3), 4),
                    delta=round(delta_p, 4),
                    in_the_money=price < strike,
                ))
            chains.append(OptionChain(symbol=sym, expiry=exp, calls=calls, puts=puts))
        return chains

    def get_earnings(self, symbol: str, quarters: int = 4) -> List[Earnings]:
        sym = symbol.upper()
        prng = _PRNG(_symbol_seed(sym) + 99)
        today = datetime.now(tz=timezone.utc)
        results = []
        for i in range(quarters):
            report_date = today - timedelta(days=90 * (i + 1))
            estimate = round(prng.uniform(0.5, 15.0), 2)
            beat = prng.random() > 0.35
            actual = round(estimate * prng.uniform(1.0 if beat else 0.7, 1.2 if beat else 0.99), 2)
            surprise = round((actual - estimate) / abs(estimate) * 100, 2) if estimate else 0
            results.append(Earnings(
                symbol=sym,
                period=report_date.strftime("%Y-Q%m"),
                report_date=report_date,
                fiscal_year=report_date.year,
                fiscal_quarter=((report_date.month - 1) // 3) + 1,
                eps_estimate=estimate,
                eps_actual=actual,
                revenue_estimate=round(prng.uniform(1e9, 1e11), 0),
                revenue_actual=round(prng.uniform(1e9, 1e11), 0),
                surprise_percent=surprise,
            ))
        return results

    def get_dividends(self, symbol: str) -> List[Dividend]:
        sym = symbol.upper()
        prng = _PRNG(_symbol_seed(sym) + 7)
        # ~50% of stocks pay dividends
        if prng.random() > 0.5:
            return []
        today = datetime.now(tz=timezone.utc)
        base_price = self._baseline(sym)
        yield_rate = prng.uniform(0.01, 0.05)
        quarterly_amount = round(base_price * yield_rate / 4, 4)
        divs = []
        for i in range(8):
            ex_date = today - timedelta(days=90 * i + 15)
            pay_date = ex_date + timedelta(days=30)
            divs.append(Dividend(
                symbol=sym, amount=quarterly_amount,
                ex_date=ex_date, pay_date=pay_date,
                frequency="quarterly", dividend_type="Cash",
                yield_percent=round(yield_rate * 100, 2),
            ))
        return divs

    def get_financials(self, symbol: str, period: str = "annual") -> List[FinancialStatement]:
        sym = symbol.upper()
        prng = _PRNG(_symbol_seed(sym) + 13)
        today = datetime.now(tz=timezone.utc)
        results = []
        n = 4 if period == "annual" else 8
        for i in range(n):
            step_days = 365 if period == "annual" else 90
            end_date = today - timedelta(days=step_days * i)
            revenue = prng.uniform(1e9, 1e11)
            gross_profit = revenue * prng.uniform(0.3, 0.7)
            op_income = gross_profit * prng.uniform(0.3, 0.8)
            net_income = op_income * prng.uniform(0.6, 0.9)
            results.append(FinancialStatement(
                symbol=sym, period=period, end_date=end_date,
                revenue=round(revenue, 0),
                gross_profit=round(gross_profit, 0),
                operating_income=round(op_income, 0),
                net_income=round(net_income, 0),
                ebitda=round(op_income * 1.15, 0),
                eps=round(net_income / prng.uniform(1e8, 1e10), 2),
                total_assets=round(prng.uniform(1e10, 1e12), 0),
                total_liabilities=round(prng.uniform(5e9, 5e11), 0),
                cash_and_equivalents=round(prng.uniform(1e9, 1e11), 0),
                free_cash_flow=round(net_income * prng.uniform(0.8, 1.2), 0),
            ))
        return results

    def get_analyst_ratings(self, symbol: str) -> List[Analyst]:
        sym = symbol.upper()
        prng = _PRNG(_symbol_seed(sym) + 17)
        price = self._baseline(sym)
        ratings = []
        for i in range(prng.randint(5, 15)):
            rating = prng.choice(_RATINGS)
            target = round(price * prng.uniform(0.7, 1.5), 2)
            days_ago = prng.randint(1, 90)
            ratings.append(Analyst(
                symbol=sym,
                firm=prng.choice(_ANALYST_FIRMS),
                analyst=None,
                rating=rating,
                target_price=target,
                date=datetime.now(tz=timezone.utc) - timedelta(days=days_ago),
                action=prng.choice(["maintain", "upgrade", "downgrade", "initiate"]),
            ))
        return ratings

    def get_insider_transactions(self, symbol: str) -> List[InsiderTransaction]:
        sym = symbol.upper()
        prng = _PRNG(_symbol_seed(sym) + 23)
        today = datetime.now(tz=timezone.utc)
        txns = []
        for i in range(prng.randint(2, 10)):
            txtype = "buy" if prng.random() > 0.4 else "sell"
            shares = prng.randint(1000, 100_000)
            price = round(self._baseline(sym) * prng.uniform(0.95, 1.05), 2)
            tx_date = today - timedelta(days=prng.randint(1, 180))
            txns.append(InsiderTransaction(
                symbol=sym,
                insider_name=f"Insider {prng.randint(1, 20)}",
                title=prng.choice(["CEO", "CFO", "COO", "Director", "VP", "SVP"]),
                transaction_type=txtype,
                shares=shares,
                price=price,
                value=shares * price,
                transaction_date=tx_date,
                filing_date=tx_date + timedelta(days=prng.randint(1, 4)),
            ))
        return txns

    def get_market_movers(self, category: str = "gainers", limit: int = 20) -> List[MarketMover]:
        prng = _PRNG(int(time.time() // 3600))
        syms = list(_TICKER_UNIVERSE.keys())[:40]
        movers = []
        for sym in syms:
            if sym.startswith("^") or sym in ("BTC", "ETH", "SOL"):
                continue
            price = self._current_price(sym)
            pct = prng.uniform(-8, 8)
            movers.append(MarketMover(
                symbol=sym, name=_TICKER_UNIVERSE[sym][0],
                price=round(price, 2),
                change=round(price * pct / 100, 4),
                change_percent=round(pct, 4),
                volume=int(prng.uniform(1e6, 1e8)),
                market_cap=round(price * prng.uniform(1e9, 3e12), 0),
            ))
        if category in ("gainers", "gainer"):
            movers.sort(key=lambda m: m.change_percent, reverse=True)
        elif category in ("losers", "loser"):
            movers.sort(key=lambda m: m.change_percent)
        else:
            movers.sort(key=lambda m: abs(m.change_percent), reverse=True)  # most active
        return movers[:limit]

    def get_market_indices(self) -> List[MarketIndex]:
        index_syms = {
            "^GSPC": "S&P 500", "^DJI": "Dow Jones Industrial Avg",
            "^IXIC": "NASDAQ Composite", "^RUT": "Russell 2000", "^VIX": "CBOE VIX",
        }
        indices = []
        for sym, name in index_syms.items():
            q = self.get_quote(sym)
            indices.append(MarketIndex(
                symbol=sym, name=name,
                price=q.price, change=q.change, change_percent=q.change_percent,
                timestamp=q.timestamp, open=q.open, high=q.high, low=q.low,
                prev_close=q.prev_close, volume=q.volume,
            ))
        return indices

    def get_sector_performance(self) -> List[SectorPerformance]:
        prng = _PRNG(int(time.time() // 3600) + 1)
        return [
            SectorPerformance(
                sector=sector,
                change_percent=round(prng.uniform(-3.0, 3.0), 4),
                timestamp=datetime.now(tz=timezone.utc),
                pe_ratio=round(prng.uniform(12, 35), 2),
            )
            for sector in _SECTOR_LIST
        ]

    def get_crypto_quote(self, symbol: str) -> CryptoQuote:
        sym = symbol.upper()
        price = self._current_price(sym)
        prng = _PRNG(_symbol_seed(sym) + int(time.time() // 60))
        prev = price * prng.uniform(0.92, 1.08)
        name = _TICKER_UNIVERSE.get(sym, (sym, "", "", 0.0))[0]
        return CryptoQuote(
            symbol=sym, name=name,
            price_usd=round(price, 6),
            market_cap_usd=round(price * prng.uniform(1e7, 1e12), 0),
            volume_24h_usd=round(prng.uniform(1e8, 1e10), 0),
            change_24h=round(price - prev, 6),
            change_percent_24h=round((price - prev) / prev * 100, 4),
            timestamp=datetime.now(tz=timezone.utc),
            circulating_supply=round(prng.uniform(1e6, 2e7), 0),
        )

    def get_forex_rate(self, base: str, quote: str) -> ForexRate:
        key = f"{base.upper()}{quote.upper()}"
        prng = _PRNG(_symbol_seed(key) + int(time.time() // 60))
        rate = round(prng.uniform(0.5, 2.0), 6)
        bid, ask = round(rate * 0.9998, 6), round(rate * 1.0002, 6)
        return ForexRate(
            base_currency=base.upper(), quote_currency=quote.upper(),
            rate=rate, bid=bid, ask=ask,
            timestamp=datetime.now(tz=timezone.utc),
            change=round(prng.uniform(-0.01, 0.01), 6),
            change_percent=round(prng.uniform(-0.5, 0.5), 4),
        )

    def get_technical_indicators(
        self,
        symbol: str,
        indicators: List[str],
        interval: Interval = Interval.DAY_1,
    ) -> List[TechnicalIndicator]:
        sym = symbol.upper()
        prng = _PRNG(_symbol_seed(sym) + int(time.time() // 300))
        price = self._current_price(sym)
        results = []
        for ind in indicators:
            ind_u = ind.upper()
            values: Dict[str, float] = {}
            if ind_u == "RSI":
                rsi = round(prng.uniform(20, 80), 2)
                values = {"RSI": rsi}
                signal = "overbought" if rsi > 70 else ("oversold" if rsi < 30 else "neutral")
            elif ind_u == "MACD":
                macd = round(prng.uniform(-5, 5), 4)
                signal_line = round(macd + prng.uniform(-1, 1), 4)
                values = {"MACD": macd, "Signal": signal_line, "Histogram": round(macd - signal_line, 4)}
                signal = "buy" if macd > signal_line else "sell"
            elif ind_u in ("BB", "BBANDS"):
                values = {
                    "Upper Band": round(price * 1.05, 4),
                    "Middle Band": round(price, 4),
                    "Lower Band": round(price * 0.95, 4),
                }
                signal = "neutral"
            elif ind_u in ("SMA", "EMA"):
                ma = round(price * prng.uniform(0.95, 1.05), 4)
                values = {ind_u: ma}
                signal = "buy" if price > ma else "sell"
            else:
                values = {ind_u: round(prng.uniform(0, 100), 4)}
                signal = "neutral"
            results.append(TechnicalIndicator(
                symbol=sym, indicator=ind_u,
                timestamp=datetime.now(tz=timezone.utc),
                values=values, signal=signal,
            ))
        return results

    def get_market_status(self) -> MarketStatus:
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

    def search_symbols(self, query: str, limit: int = 10) -> List[Dict]:
        q = query.upper()
        results = []
        for sym, (name, sector, industry, _) in _TICKER_UNIVERSE.items():
            if q in sym or q.lower() in name.lower():
                results.append({
                    "symbol": sym, "name": name,
                    "type": "Index" if sym.startswith("^") else "Equity",
                    "sector": sector,
                })
            if len(results) >= limit:
                break
        return results

    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset simulated prices to baseline values."""
        with self._lock:
            if symbol:
                sym = symbol.upper()
                self._prices.pop(sym, None)
                self._last_tick.pop(sym, None)
            else:
                self._prices.clear()
                self._last_tick.clear()


# ---------------------------------------------------------------------------
# Black-Scholes helper for option pricing
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Approximation of the standard normal CDF."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bs_option(
    S: float, K: float, T: float, r: float, sigma: float, opt_type: str
) -> Tuple[float, float, float]:
    """Return (bid, ask, delta) for a European option via Black-Scholes."""
    if T <= 0:
        intrinsic = max(S - K, 0) if opt_type == "call" else max(K - S, 0)
        return round(intrinsic * 0.99, 2), round(intrinsic * 1.01, 2), (1.0 if opt_type == "call" else -1.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt_type == "call":
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
    else:
        price = K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1
    half_spread = max(price * 0.01, 0.01)
    bid = round(max(price - half_spread, 0.01), 2)
    ask = round(price + half_spread, 2)
    return bid, ask, round(delta, 4)
