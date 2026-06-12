'use client';

import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { PortfolioSnapshot } from '@/lib/api';

interface PLChartProps {
  history: PortfolioSnapshot[];
}

export default function PLChart({ history }: PLChartProps) {
  const formatTime = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  };

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(val);

  const data = history.map(s => ({
    time: formatTime(s.recorded_at),
    value: s.total_value,
    rawTime: s.recorded_at,
  }));

  const minVal = data.length > 0 ? Math.min(...data.map(d => d.value)) : 0;
  const maxVal = data.length > 0 ? Math.max(...data.map(d => d.value)) : 10000;
  const domain = [Math.floor(minVal * 0.999), Math.ceil(maxVal * 1.001)];

  const latestValue = data.length > 0 ? data[data.length - 1].value : null;
  const firstValue = data.length > 0 ? data[0].value : null;
  const totalChange = latestValue !== null && firstValue !== null ? latestValue - firstValue : null;
  const totalChangePct =
    totalChange !== null && firstValue && firstValue > 0
      ? (totalChange / firstValue) * 100
      : null;

  const lineColor =
    totalChange === null ? '#209dd7' : totalChange >= 0 ? '#22c55e' : '#ef4444';

  return (
    <div
      className="h-full flex flex-col"
      style={{ background: '#1a1a2e', border: '1px solid #30363d' }}
    >
      <div
        className="px-3 py-2 border-b shrink-0 flex items-center justify-between"
        style={{ borderColor: '#30363d' }}
      >
        <span className="text-xs font-bold tracking-widest" style={{ color: '#8b949e' }}>
          PORTFOLIO P&L
        </span>
        {latestValue !== null && (
          <div className="flex items-center gap-3 text-xs">
            <span style={{ color: '#e6edf3' }}>{formatCurrency(latestValue)}</span>
            {totalChange !== null && (
              <span style={{ color: lineColor }}>
                {totalChange >= 0 ? '+' : ''}
                {formatCurrency(totalChange)}{' '}
                {totalChangePct !== null && (
                  <>({totalChangePct >= 0 ? '+' : ''}{totalChangePct.toFixed(2)}%)</>
                )}
              </span>
            )}
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0 pt-2">
        {data.length < 2 ? (
          <div
            className="h-full flex items-center justify-center text-xs"
            style={{ color: '#484f58' }}
          >
            Collecting portfolio history...
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis
                dataKey="time"
                tick={{ fill: '#8b949e', fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: '#30363d' }}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={domain}
                tick={{ fill: '#8b949e', fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: '#30363d' }}
                tickFormatter={v => `$${(v / 1000).toFixed(1)}k`}
                width={48}
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div
                      className="px-3 py-2 text-xs rounded"
                      style={{
                        background: '#21262d',
                        border: '1px solid #30363d',
                        color: '#e6edf3',
                      }}
                    >
                      <div style={{ color: '#8b949e' }}>{label}</div>
                      <div className="font-bold">
                        {formatCurrency(payload[0].value as number)}
                      </div>
                    </div>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={lineColor}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
