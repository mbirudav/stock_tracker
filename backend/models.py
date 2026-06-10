from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class DataProvider(str, Enum):
    YAHOO_FINANCE = "yahoo_finance"
    ALPHA_VANTAGE = "alpha_vantage"
    POLYGON = "polygon"
    FINNHUB = "finnhub"
    SIMULATOR = "simulator"


class Interval(str, Enum):
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    DAY_1 = "1d"
    WEEK_1 = "1wk"
    MONTH_1 = "1mo"


class Period(str, Enum):
    DAY_1 = "1d"
    WEEK_1 = "5d"
    MONTH_1 = "1mo"
    MONTH_3 = "3mo"
    MONTH_6 = "6mo"
    YEAR_1 = "1y"
    YEAR_2 = "2y"
    YEAR_5 = "5y"
    YEAR_10 = "10y"
    MAX = "max"


class MarketStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"


@dataclass
class Quote:
    symbol: str
    price: float
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: int
    timestamp: datetime
    provider: DataProvider
    change: float = 0.0
    change_percent: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    average_volume: Optional[int] = None
    shares_outstanding: Optional[float] = None


@dataclass
class OHLCV:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None
    dividends: Optional[float] = None
    stock_splits: Optional[float] = None


@dataclass
class CompanyInfo:
    symbol: str
    name: str
    sector: str
    industry: str
    description: str
    employees: Optional[int] = None
    website: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    country: Optional[str] = None
    ipo_date: Optional[str] = None
    market_cap: Optional[float] = None
    shares_outstanding: Optional[float] = None
    float_shares: Optional[float] = None
    beta: Optional[float] = None
    forward_pe: Optional[float] = None
    trailing_pe: Optional[float] = None
    price_to_book: Optional[float] = None
    profit_margins: Optional[float] = None
    revenue_growth: Optional[float] = None


@dataclass
class NewsItem:
    id: str
    headline: str
    summary: str
    url: str
    source: str
    timestamp: datetime
    symbols: List[str] = field(default_factory=list)
    sentiment: Optional[float] = None  # -1.0 (negative) to 1.0 (positive)
    category: Optional[str] = None
    image_url: Optional[str] = None


@dataclass
class OptionContract:
    symbol: str
    underlying: str
    expiry: datetime
    strike: float
    option_type: str  # 'call' or 'put'
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    in_the_money: Optional[bool] = None
    percent_change: Optional[float] = None


@dataclass
class OptionChain:
    symbol: str
    expiry: datetime
    calls: List[OptionContract] = field(default_factory=list)
    puts: List[OptionContract] = field(default_factory=list)


@dataclass
class MarketIndex:
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    timestamp: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[int] = None


@dataclass
class Dividend:
    symbol: str
    amount: float
    ex_date: datetime
    pay_date: datetime
    frequency: str  # 'quarterly', 'monthly', 'annual', 'semi-annual'
    dividend_type: str  # 'Cash', 'Stock'
    declaration_date: Optional[datetime] = None
    yield_percent: Optional[float] = None


@dataclass
class Earnings:
    symbol: str
    period: str
    report_date: datetime
    fiscal_year: int
    fiscal_quarter: int
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None
    surprise_percent: Optional[float] = None


@dataclass
class FinancialStatement:
    symbol: str
    period: str  # 'annual' or 'quarterly'
    end_date: datetime
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    ebitda: Optional[float] = None
    eps: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    total_debt: Optional[float] = None
    free_cash_flow: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    capital_expenditures: Optional[float] = None


@dataclass
class Analyst:
    symbol: str
    firm: str
    analyst: Optional[str]
    rating: str
    target_price: Optional[float]
    date: datetime
    previous_rating: Optional[str] = None
    previous_target: Optional[float] = None
    action: Optional[str] = None  # 'upgrade', 'downgrade', 'maintain', 'initiate'


@dataclass
class InsiderTransaction:
    symbol: str
    insider_name: str
    title: str
    transaction_type: str  # 'buy' or 'sell'
    shares: int
    price: float
    value: float
    transaction_date: datetime
    filing_date: datetime
    shares_owned_after: Optional[int] = None


@dataclass
class MarketMover:
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    volume: int
    market_cap: Optional[float] = None


@dataclass
class SectorPerformance:
    sector: str
    change_percent: float
    timestamp: datetime
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None


@dataclass
class EconomicIndicator:
    name: str
    value: float
    previous_value: Optional[float]
    unit: str
    release_date: datetime
    next_release: Optional[datetime] = None
    country: str = "US"


@dataclass
class CryptoQuote:
    symbol: str
    name: str
    price_usd: float
    market_cap_usd: float
    volume_24h_usd: float
    change_24h: float
    change_percent_24h: float
    timestamp: datetime
    circulating_supply: Optional[float] = None
    total_supply: Optional[float] = None
    all_time_high: Optional[float] = None


@dataclass
class ForexRate:
    base_currency: str
    quote_currency: str
    rate: float
    bid: float
    ask: float
    timestamp: datetime
    change: Optional[float] = None
    change_percent: Optional[float] = None


@dataclass
class TechnicalIndicator:
    symbol: str
    indicator: str
    timestamp: datetime
    values: Dict[str, float] = field(default_factory=dict)
    signal: Optional[str] = None  # 'buy', 'sell', 'neutral'
