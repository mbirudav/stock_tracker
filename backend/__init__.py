"""
Stock Tracker — Market Data Backend

Quick start::

    from backend.massive_api_interface import MassiveAPIInterface
    from backend.market_data_simulator import MarketDataSimulator

    # Use real APIs (Yahoo Finance is free, others need API keys)
    api = MassiveAPIInterface()
    quote = api.get_quote("AAPL")

    # Or use the simulator for dev/testing
    from backend.unified_market_data import UnifiedMarketData
    sim = MarketDataSimulator()
    umd = UnifiedMarketData(providers=[sim])
    quote = umd.get_quote("AAPL")
"""

from .config import Config, get_config, set_config
from .market_data_simulator import MarketDataSimulator
from .massive_api_interface import (
    AlphaVantageProvider,
    FinnhubProvider,
    MassiveAPIInterface,
    PolygonProvider,
    YahooFinanceProvider,
)
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
from .unified_market_data import MarketDataProvider, UnifiedMarketData

__all__ = [
    # Config
    "Config", "get_config", "set_config",
    # Unified interface
    "MarketDataProvider", "UnifiedMarketData",
    # Implementations
    "MassiveAPIInterface",
    "YahooFinanceProvider", "AlphaVantageProvider", "PolygonProvider", "FinnhubProvider",
    "MarketDataSimulator",
    # Models
    "DataProvider", "Interval", "Period", "MarketStatus",
    "Quote", "OHLCV", "CompanyInfo", "NewsItem",
    "OptionContract", "OptionChain", "MarketIndex", "Dividend", "Earnings",
    "FinancialStatement", "Analyst", "InsiderTransaction", "MarketMover",
    "SectorPerformance", "CryptoQuote", "ForexRate", "TechnicalIndicator",
]
