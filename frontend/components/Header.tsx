'use client';

import React from 'react';
import { ConnectionStatus } from '@/hooks/useMarketData';

interface HeaderProps {
  totalValue: number;
  cashBalance: number;
  connectionStatus: ConnectionStatus;
}

function ConnectionDot({ status }: { status: ConnectionStatus }) {
  const colors: Record<ConnectionStatus, string> = {
    connected: '#22c55e',
    reconnecting: '#ecad0a',
    disconnected: '#ef4444',
  };
  const labels: Record<ConnectionStatus, string> = {
    connected: 'LIVE',
    reconnecting: 'RECONNECTING',
    disconnected: 'DISCONNECTED',
  };

  return (
    <div className="flex items-center gap-1.5">
      <div
        className="w-2 h-2 rounded-full"
        style={{
          backgroundColor: colors[status],
          boxShadow: status === 'connected' ? `0 0 6px ${colors[status]}` : 'none',
        }}
      />
      <span className="text-xs" style={{ color: colors[status] }}>
        {labels[status]}
      </span>
    </div>
  );
}

export default function Header({ totalValue, cashBalance, connectionStatus }: HeaderProps) {
  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(val);

  return (
    <header
      className="flex items-center justify-between px-4 py-2 border-b shrink-0"
      style={{
        background: '#0d1117',
        borderColor: '#30363d',
        height: '48px',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3">
        <span
          className="text-xl font-black tracking-widest"
          style={{ color: '#ecad0a', letterSpacing: '0.15em' }}
        >
          FIN<span style={{ color: '#209dd7' }}>ALLY</span>
        </span>
        <span className="text-xs" style={{ color: '#8b949e' }}>
          AI Trading Workstation
        </span>
      </div>

      {/* Portfolio metrics */}
      <div className="flex items-center gap-6">
        <div className="flex flex-col items-end">
          <span className="text-xs" style={{ color: '#8b949e' }}>
            PORTFOLIO
          </span>
          <span className="text-sm font-bold" style={{ color: '#e6edf3' }}>
            {formatCurrency(totalValue)}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-xs" style={{ color: '#8b949e' }}>
            CASH
          </span>
          <span className="text-sm font-bold" style={{ color: '#22c55e' }}>
            {formatCurrency(cashBalance)}
          </span>
        </div>
        <div
          className="w-px h-6"
          style={{ background: '#30363d' }}
        />
        <ConnectionDot status={connectionStatus} />
      </div>
    </header>
  );
}
