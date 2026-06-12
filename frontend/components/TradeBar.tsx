'use client';

import React, { useState, useCallback } from 'react';
import { api } from '@/lib/api';

interface TradeBarProps {
  selectedTicker?: string | null;
  onTradeSuccess?: () => void;
}

export default function TradeBar({ selectedTicker, onTradeSuccess }: TradeBarProps) {
  const [ticker, setTicker] = useState('');
  const [quantity, setQuantity] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  // Fill ticker from selected ticker
  React.useEffect(() => {
    if (selectedTicker) {
      setTicker(selectedTicker);
    }
  }, [selectedTicker]);

  const executeTrade = useCallback(
    async (side: 'buy' | 'sell') => {
      const t = ticker.trim().toUpperCase();
      const q = parseFloat(quantity);

      if (!t) {
        setError('Enter a ticker symbol');
        return;
      }
      if (!q || q <= 0 || isNaN(q)) {
        setError('Enter a valid quantity');
        return;
      }

      setLoading(true);
      setError('');
      setSuccess('');

      try {
        const result = await api.executeTrade({ ticker: t, quantity: q, side });
        if (result.success && result.trade) {
          const { side: s, quantity: qty, price } = result.trade;
          setSuccess(
            `${s.toUpperCase()} ${qty} ${t} @ $${price.toFixed(2)}`
          );
          setQuantity('');
          onTradeSuccess?.();
          setTimeout(() => setSuccess(''), 4000);
        } else if (result.error) {
          setError(result.error);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Trade failed');
      } finally {
        setLoading(false);
      }
    },
    [ticker, quantity, onTradeSuccess]
  );

  return (
    <div
      className="px-3 py-2 border-t shrink-0 flex items-center gap-3"
      style={{
        background: '#0d1117',
        borderColor: '#30363d',
        height: '52px',
      }}
    >
      <span className="text-xs font-bold tracking-widest shrink-0" style={{ color: '#8b949e' }}>
        TRADE
      </span>

      {/* Ticker input */}
      <input
        type="text"
        value={ticker}
        onChange={e => {
          setTicker(e.target.value.toUpperCase());
          setError('');
        }}
        placeholder="TICKER"
        className="w-20 px-2 py-1 text-xs rounded text-center"
        style={{
          background: '#1a1a2e',
          border: '1px solid #30363d',
          color: '#ecad0a',
          outline: 'none',
          fontWeight: 'bold',
        }}
        disabled={loading}
      />

      {/* Quantity input */}
      <input
        type="number"
        value={quantity}
        onChange={e => {
          setQuantity(e.target.value);
          setError('');
        }}
        onKeyDown={e => {
          if (e.key === 'Enter') executeTrade('buy');
        }}
        placeholder="QTY"
        className="w-20 px-2 py-1 text-xs rounded"
        style={{
          background: '#1a1a2e',
          border: '1px solid #30363d',
          color: '#e6edf3',
          outline: 'none',
        }}
        min="0"
        step="1"
        disabled={loading}
      />

      {/* Buy button */}
      <button
        onClick={() => executeTrade('buy')}
        disabled={loading}
        className="px-4 py-1.5 text-xs font-bold rounded"
        style={{
          background: loading ? '#21262d' : '#753991',
          color: loading ? '#484f58' : '#fff',
          border: 'none',
          cursor: loading ? 'not-allowed' : 'pointer',
          letterSpacing: '0.05em',
        }}
      >
        BUY
      </button>

      {/* Sell button */}
      <button
        onClick={() => executeTrade('sell')}
        disabled={loading}
        className="px-4 py-1.5 text-xs font-bold rounded"
        style={{
          background: loading ? '#21262d' : 'transparent',
          color: loading ? '#484f58' : '#753991',
          border: `1px solid ${loading ? '#30363d' : '#753991'}`,
          cursor: loading ? 'not-allowed' : 'pointer',
          letterSpacing: '0.05em',
        }}
      >
        SELL
      </button>

      {/* Feedback */}
      <div className="flex-1">
        {error && (
          <span className="text-xs" style={{ color: '#ef4444' }}>
            {error}
          </span>
        )}
        {success && (
          <span className="text-xs font-bold" style={{ color: '#22c55e' }}>
            ✓ {success}
          </span>
        )}
      </div>
    </div>
  );
}
