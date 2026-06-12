'use client';

import React from 'react';
import { Portfolio } from '@/lib/api';

interface PositionsTableProps {
  portfolio: Portfolio | null;
  onSelectTicker?: (ticker: string) => void;
}

export default function PositionsTable({ portfolio, onSelectTicker }: PositionsTableProps) {
  const positions = portfolio?.positions ?? [];

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);

  return (
    <div
      className="h-full flex flex-col"
      style={{ background: '#1a1a2e', borderTop: '1px solid #30363d' }}
    >
      <div
        className="px-3 py-2 border-b shrink-0 flex items-center justify-between"
        style={{ borderColor: '#30363d' }}
      >
        <span className="text-xs font-bold tracking-widest" style={{ color: '#8b949e' }}>
          POSITIONS
        </span>
        <span className="text-xs" style={{ color: '#484f58' }}>
          {positions.length} open
        </span>
      </div>

      {/* Table header */}
      <div
        className="grid px-3 py-1 border-b shrink-0"
        style={{
          borderColor: '#30363d',
          gridTemplateColumns: '64px 60px 80px 80px 80px 72px',
          color: '#484f58',
          fontSize: 10,
          letterSpacing: '0.05em',
        }}
      >
        <span>TICKER</span>
        <span className="text-right">QTY</span>
        <span className="text-right">AVG COST</span>
        <span className="text-right">CURRENT</span>
        <span className="text-right">P&L $</span>
        <span className="text-right">P&L %</span>
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto">
        {positions.length === 0 ? (
          <div
            className="flex items-center justify-center py-6 text-xs"
            style={{ color: '#484f58' }}
          >
            No open positions
          </div>
        ) : (
          positions.map(pos => {
            const isProfit = pos.unrealized_pnl >= 0;
            const pnlColor = isProfit ? '#22c55e' : '#ef4444';

            return (
              <div
                key={pos.ticker}
                className="grid px-3 py-1.5 border-b cursor-pointer items-center"
                style={{
                  borderColor: '#21262d',
                  gridTemplateColumns: '64px 60px 80px 80px 80px 72px',
                  transition: 'background-color 0.1s',
                }}
                onClick={() => onSelectTicker?.(pos.ticker)}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLDivElement).style.background = '#21262d';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                }}
              >
                <span className="text-xs font-bold" style={{ color: '#ecad0a' }}>
                  {pos.ticker}
                </span>
                <span className="text-xs text-right font-mono" style={{ color: '#e6edf3' }}>
                  {pos.quantity % 1 === 0 ? pos.quantity : pos.quantity.toFixed(2)}
                </span>
                <span className="text-xs text-right font-mono" style={{ color: '#8b949e' }}>
                  ${pos.avg_cost.toFixed(2)}
                </span>
                <span className="text-xs text-right font-mono" style={{ color: '#e6edf3' }}>
                  ${pos.current_price.toFixed(2)}
                </span>
                <span className="text-xs text-right font-mono font-bold" style={{ color: pnlColor }}>
                  {pos.unrealized_pnl >= 0 ? '+' : ''}
                  {formatCurrency(pos.unrealized_pnl)}
                </span>
                <span className="text-xs text-right font-mono" style={{ color: pnlColor }}>
                  {pos.pnl_pct >= 0 ? '+' : ''}
                  {pos.pnl_pct.toFixed(2)}%
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
