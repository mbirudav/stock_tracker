'use client';

import React, { useState, useCallback } from 'react';
import {
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import { PriceData } from '@/hooks/useMarketData';
import { api } from '@/lib/api';

interface WatchlistPanelProps {
  tickers: string[];
  prices: Record<string, PriceData>;
  priceHistory: Record<string, number[]>;
  flashingTickers: Record<string, 'up' | 'down'>;
  selectedTicker: string | null;
  onSelectTicker: (ticker: string) => void;
  onWatchlistUpdate: () => void;
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data || data.length < 2) {
    return (
      <div
        className="flex items-center justify-center"
        style={{ width: 80, height: 36, color: '#484f58', fontSize: 10 }}
      >
        --
      </div>
    );
  }

  const chartData = data.map((v, i) => ({ i, v }));

  return (
    <ResponsiveContainer width={80} height={36}>
      <LineChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function WatchlistPanel({
  tickers,
  prices,
  priceHistory,
  flashingTickers,
  selectedTicker,
  onSelectTicker,
  onWatchlistUpdate,
}: WatchlistPanelProps) {
  const [addInput, setAddInput] = useState('');
  const [addError, setAddError] = useState('');
  const [adding, setAdding] = useState(false);

  const firstPrices = React.useRef<Record<string, number>>({});

  // Track first-seen price per ticker for change% calculation
  React.useEffect(() => {
    tickers.forEach(ticker => {
      const pd = prices[ticker];
      if (pd && !firstPrices.current[ticker]) {
        firstPrices.current[ticker] = pd.price;
      }
    });
  }, [tickers, prices]);

  const getChangePercent = (ticker: string): number | null => {
    const pd = prices[ticker];
    const first = firstPrices.current[ticker];
    if (!pd || !first) return null;
    return ((pd.price - first) / first) * 100;
  };

  const formatPrice = (price: number) =>
    price < 10
      ? price.toFixed(4)
      : price.toFixed(2);

  const handleAdd = useCallback(async () => {
    const t = addInput.trim().toUpperCase();
    if (!t) return;
    setAdding(true);
    setAddError('');
    try {
      await api.addToWatchlist(t);
      setAddInput('');
      onWatchlistUpdate();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to add ticker');
    } finally {
      setAdding(false);
    }
  }, [addInput, onWatchlistUpdate]);

  const handleRemove = useCallback(
    async (ticker: string, e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        await api.removeFromWatchlist(ticker);
        onWatchlistUpdate();
      } catch {
        // silently fail
      }
    },
    [onWatchlistUpdate]
  );

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: '#1a1a2e', borderRight: '1px solid #30363d' }}
    >
      {/* Panel header */}
      <div
        className="px-3 py-2 border-b flex items-center justify-between shrink-0"
        style={{ borderColor: '#30363d' }}
      >
        <span className="text-xs font-bold tracking-widest" style={{ color: '#8b949e' }}>
          WATCHLIST
        </span>
        <span className="text-xs" style={{ color: '#484f58' }}>
          {tickers.length} tickers
        </span>
      </div>

      {/* Column headers */}
      <div
        className="grid px-3 py-1 border-b shrink-0"
        style={{
          borderColor: '#30363d',
          gridTemplateColumns: '56px 1fr 52px 80px 16px',
          color: '#484f58',
          fontSize: 10,
          letterSpacing: '0.05em',
        }}
      >
        <span>TICKER</span>
        <span className="text-right">PRICE</span>
        <span className="text-right">CHG%</span>
        <span className="text-right">CHART</span>
        <span />
      </div>

      {/* Ticker rows */}
      <div className="flex-1 overflow-y-auto">
        {tickers.map(ticker => {
          const pd = prices[ticker];
          const flash = flashingTickers[ticker];
          const changePercent = getChangePercent(ticker);
          const isSelected = selectedTicker === ticker;
          const history = priceHistory[ticker] ?? [];

          const sparklineColor =
            changePercent === null
              ? '#8b949e'
              : changePercent >= 0
              ? '#22c55e'
              : '#ef4444';

          let flashClass = '';
          if (flash === 'up') flashClass = 'flash-green';
          else if (flash === 'down') flashClass = 'flash-red';

          return (
            <div
              key={ticker}
              className={`grid px-3 py-1.5 cursor-pointer border-b items-center ${flashClass}`}
              style={{
                borderColor: '#21262d',
                gridTemplateColumns: '56px 1fr 52px 80px 16px',
                background: isSelected ? '#21262d' : 'transparent',
                transition: 'background-color 0.15s',
              }}
              onClick={() => onSelectTicker(ticker)}
            >
              {/* Ticker symbol */}
              <div className="flex items-center gap-1">
                <span
                  className="font-bold text-xs"
                  style={{ color: '#ecad0a' }}
                >
                  {ticker}
                </span>
              </div>

              {/* Price */}
              <div className="text-right">
                <span className="text-xs font-mono" style={{ color: '#e6edf3' }}>
                  {pd ? formatPrice(pd.price) : '--'}
                </span>
              </div>

              {/* Change % */}
              <div className="text-right">
                {changePercent !== null ? (
                  <span
                    className="text-xs font-mono"
                    style={{ color: changePercent >= 0 ? '#22c55e' : '#ef4444' }}
                  >
                    {changePercent >= 0 ? '+' : ''}
                    {changePercent.toFixed(2)}%
                  </span>
                ) : (
                  <span className="text-xs" style={{ color: '#484f58' }}>
                    --
                  </span>
                )}
              </div>

              {/* Sparkline */}
              <div className="flex items-center justify-end">
                <Sparkline data={history} color={sparklineColor} />
              </div>

              {/* Remove button */}
              <div className="flex items-center justify-end">
                <button
                  aria-label={`Remove ${ticker}`}
                  title={`Remove ${ticker} from watchlist`}
                  onClick={e => handleRemove(ticker, e)}
                  className="text-xs leading-none px-0.5"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#484f58',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLButtonElement).style.color = '#ef4444';
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.color = '#484f58';
                  }}
                >
                  ×
                </button>
              </div>
            </div>
          );
        })}

        {tickers.length === 0 && (
          <div
            className="flex items-center justify-center py-8 text-xs"
            style={{ color: '#484f58' }}
          >
            No tickers in watchlist
          </div>
        )}
      </div>

      {/* Add ticker input */}
      <div
        className="px-3 py-2 border-t shrink-0"
        style={{ borderColor: '#30363d' }}
      >
        {addError && (
          <div className="text-xs mb-1" style={{ color: '#ef4444' }}>
            {addError}
          </div>
        )}
        <div className="flex gap-1">
          <input
            type="text"
            value={addInput}
            onChange={e => setAddInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="ADD TICKER"
            className="flex-1 px-2 py-1 text-xs rounded"
            style={{
              background: '#0d1117',
              border: '1px solid #30363d',
              color: '#e6edf3',
              outline: 'none',
            }}
            disabled={adding}
          />
          <button
            onClick={handleAdd}
            disabled={adding || !addInput.trim()}
            className="px-2 py-1 text-xs rounded font-bold"
            style={{
              background: adding || !addInput.trim() ? '#21262d' : '#209dd7',
              color: adding || !addInput.trim() ? '#484f58' : '#fff',
              border: 'none',
              cursor: adding || !addInput.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            +
          </button>
        </div>
      </div>
    </div>
  );
}
