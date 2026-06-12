'use client';

import React, { useState, useEffect } from 'react';
import Header from '@/components/Header';
import WatchlistPanel from '@/components/WatchlistPanel';
import MainChart from '@/components/MainChart';
import PortfolioHeatmap from '@/components/PortfolioHeatmap';
import PLChart from '@/components/PLChart';
import PositionsTable from '@/components/PositionsTable';
import TradeBar from '@/components/TradeBar';
import ChatPanel from '@/components/ChatPanel';
import { useMarketData } from '@/hooks/useMarketData';
import { usePortfolio, usePortfolioHistory, useWatchlist } from '@/hooks/usePortfolio';

export default function TradingWorkstation() {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  const { prices, priceHistory, connectionStatus, flashingTickers } = useMarketData();
  const { portfolio, refresh: refreshPortfolio } = usePortfolio(5000);
  const { history: portfolioHistory, refresh: refreshHistory } = usePortfolioHistory(10000);
  const { watchlist, refresh: refreshWatchlist } = useWatchlist();

  // Auto-select first ticker
  useEffect(() => {
    if (!selectedTicker && watchlist.length > 0) {
      setSelectedTicker(watchlist[0]);
    }
  }, [watchlist, selectedTicker]);

  const handleTradeSuccess = () => {
    refreshPortfolio();
    refreshHistory();
  };

  const handleWatchlistUpdate = () => {
    refreshWatchlist();
  };

  return (
    <div
      className="flex flex-col h-screen overflow-hidden"
      style={{ background: '#0d1117', color: '#e6edf3' }}
    >
      {/* Header */}
      <Header
        totalValue={portfolio?.total_value ?? 10000}
        cashBalance={portfolio?.cash_balance ?? 10000}
        connectionStatus={connectionStatus}
      />

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Left: Watchlist */}
        <div className="flex-none overflow-hidden" style={{ width: '220px' }}>
          <WatchlistPanel
            tickers={watchlist}
            prices={prices}
            priceHistory={priceHistory}
            flashingTickers={flashingTickers}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
            onWatchlistUpdate={handleWatchlistUpdate}
          />
        </div>

        {/* Center: Chart + Heatmap/P&L */}
        <div className="flex-1 flex flex-col overflow-hidden min-h-0 min-w-0">
          {/* Main chart */}
          <div className="flex-1 overflow-hidden min-h-0" style={{ minHeight: '220px' }}>
            <MainChart
              selectedTicker={selectedTicker}
              prices={prices}
              priceHistory={priceHistory}
            />
          </div>

          {/* Heatmap + P&L side by side */}
          <div
            className="flex overflow-hidden shrink-0"
            style={{ height: '200px', borderTop: '1px solid #30363d' }}
          >
            <div className="flex-1 overflow-hidden" style={{ minWidth: 0 }}>
              <PortfolioHeatmap portfolio={portfolio} />
            </div>
            <div
              className="flex-1 overflow-hidden"
              style={{ minWidth: 0, borderLeft: '1px solid #30363d' }}
            >
              <PLChart history={portfolioHistory} />
            </div>
          </div>
        </div>

        {/* Right: Chat panel */}
        <div className="flex-none overflow-hidden" style={{ width: '280px' }}>
          <ChatPanel
            onTradeSuccess={handleTradeSuccess}
            onWatchlistUpdate={handleWatchlistUpdate}
          />
        </div>
      </div>

      {/* Bottom: Trade bar + Positions table */}
      <div
        className="shrink-0 flex flex-col"
        style={{ height: '180px', borderTop: '1px solid #30363d' }}
      >
        <TradeBar
          selectedTicker={selectedTicker}
          onTradeSuccess={handleTradeSuccess}
        />
        <div className="flex-1 overflow-hidden min-h-0">
          <PositionsTable
            portfolio={portfolio}
            onSelectTicker={setSelectedTicker}
          />
        </div>
      </div>
    </div>
  );
}
