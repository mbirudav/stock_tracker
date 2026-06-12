'use client';

import React from 'react';
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts';
import { Portfolio } from '@/lib/api';

interface PortfolioHeatmapProps {
  portfolio: Portfolio | null;
}

function lerpColor(t: number): string {
  // t in [-1, 1], -1 = full red, 0 = neutral gray, 1 = full green
  const clamped = Math.max(-1, Math.min(1, t));
  if (clamped >= 0) {
    // gray (#4a4a5a) to green (#22c55e)
    const r = Math.round(74 + (34 - 74) * clamped);
    const g = Math.round(74 + (197 - 74) * clamped);
    const b = Math.round(90 + (94 - 90) * clamped);
    return `rgb(${r},${g},${b})`;
  } else {
    // red (#ef4444) to gray (#4a4a5a)
    const abs = Math.abs(clamped);
    const r = Math.round(74 + (239 - 74) * abs);
    const g = Math.round(74 + (68 - 74) * abs);
    const b = Math.round(90 + (68 - 90) * abs);
    return `rgb(${r},${g},${b})`;
  }
}

interface TreemapEntry {
  name: string;
  size: number;
  pnl: number;
  pnlPercent: number;
  color: string;
  [key: string]: unknown;
}

// Custom cell renderer for treemap
function CustomContent(props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnlPercent?: number;
  color?: string;
}) {
  const { x = 0, y = 0, width = 0, height = 0, name, pnlPercent, color } = props;
  if (width < 20 || height < 20) return null;

  const fontSize = width > 80 ? 13 : 10;

  return (
    <g>
      <rect
        x={x + 1}
        y={y + 1}
        width={width - 2}
        height={height - 2}
        fill={color}
        stroke="#0d1117"
        strokeWidth={2}
        rx={3}
      />
      {height > 30 && (
        <text
          x={x + width / 2}
          y={y + height / 2 - (height > 45 ? 8 : 0)}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#fff"
          fontSize={fontSize}
          fontWeight="bold"
          fontFamily="ui-monospace, monospace"
        >
          {name}
        </text>
      )}
      {height > 45 && pnlPercent !== undefined && (
        <text
          x={x + width / 2}
          y={y + height / 2 + 10}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="rgba(255,255,255,0.8)"
          fontSize={10}
          fontFamily="ui-monospace, monospace"
        >
          {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(1)}%
        </text>
      )}
    </g>
  );
}

export default function PortfolioHeatmap({ portfolio }: PortfolioHeatmapProps) {
  if (!portfolio || portfolio.positions.length === 0) {
    return (
      <div
        className="h-full flex flex-col"
        style={{ background: '#1a1a2e', border: '1px solid #30363d' }}
      >
        <div
          className="px-3 py-2 border-b shrink-0"
          style={{ borderColor: '#30363d' }}
        >
          <span className="text-xs font-bold tracking-widest" style={{ color: '#8b949e' }}>
            PORTFOLIO HEATMAP
          </span>
        </div>
        <div
          className="flex-1 flex items-center justify-center text-xs"
          style={{ color: '#484f58' }}
        >
          No positions yet
        </div>
      </div>
    );
  }

  const totalPositionValue = portfolio.positions.reduce(
    (sum, p) => sum + p.current_price * p.quantity,
    0
  );

  const data: TreemapEntry[] = portfolio.positions.map(pos => {
    const positionValue = pos.current_price * pos.quantity;
    const weight = totalPositionValue > 0 ? positionValue / totalPositionValue : 0;
    // Normalize pnl percent to [-1, 1] range for color lerp
    // Cap at ±20% for color scaling
    const normalizedPnl = Math.max(-1, Math.min(1, pos.pnl_pct / 20));
    return {
      name: pos.ticker,
      size: Math.max(weight * 1000, 10), // recharts treemap needs positive size
      pnl: pos.unrealized_pnl,
      pnlPercent: pos.pnl_pct,
      color: lerpColor(normalizedPnl),
    };
  });

  return (
    <div
      className="h-full flex flex-col"
      style={{ background: '#1a1a2e', border: '1px solid #30363d' }}
    >
      <div
        className="px-3 py-2 border-b shrink-0"
        style={{ borderColor: '#30363d' }}
      >
        <span className="text-xs font-bold tracking-widest" style={{ color: '#8b949e' }}>
          PORTFOLIO HEATMAP
        </span>
      </div>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={data}
            dataKey="size"
            aspectRatio={4 / 3}
            content={<CustomContent />}
          >
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const entry = payload[0].payload as TreemapEntry;
                return (
                  <div
                    className="px-3 py-2 text-xs rounded"
                    style={{
                      background: '#21262d',
                      border: '1px solid #30363d',
                      color: '#e6edf3',
                    }}
                  >
                    <div className="font-bold" style={{ color: '#ecad0a' }}>
                      {entry.name}
                    </div>
                    <div>
                      P&L:{' '}
                      <span style={{ color: entry.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        {entry.pnl >= 0 ? '+' : ''}${entry.pnl.toFixed(2)} (
                        {entry.pnlPercent >= 0 ? '+' : ''}
                        {entry.pnlPercent.toFixed(2)}%)
                      </span>
                    </div>
                  </div>
                );
              }}
            />
          </Treemap>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
