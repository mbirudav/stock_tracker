'use client';

import React, { useEffect, useRef } from 'react';
import { PriceData } from '@/hooks/useMarketData';

interface MainChartProps {
  selectedTicker: string | null;
  prices: Record<string, PriceData>;
  priceHistory: Record<string, number[]>;
}

type IChartApi = import('lightweight-charts').IChartApi;
type ISeriesApi = import('lightweight-charts').ISeriesApi<'Line'>;

export default function MainChart({ selectedTicker, prices, priceHistory }: MainChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi | null>(null);
  const prevTickerRef = useRef<string | null>(null);

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    let chart: IChartApi | null = null;
    let ro: ResizeObserver | null = null;

    import('lightweight-charts').then(({ createChart, ColorType, LineSeries }) => {
      if (!containerRef.current) return;

      chart = createChart(containerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: '#0d1117' },
          textColor: '#8b949e',
        },
        grid: {
          vertLines: { color: '#21262d' },
          horzLines: { color: '#21262d' },
        },
        crosshair: {
          vertLine: { color: '#484f58', labelBackgroundColor: '#21262d' },
          horzLine: { color: '#484f58', labelBackgroundColor: '#21262d' },
        },
        timeScale: {
          borderColor: '#30363d',
          timeVisible: true,
          secondsVisible: true,
        },
        rightPriceScale: {
          borderColor: '#30363d',
        },
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });

      const series = chart.addSeries(LineSeries, {
        color: '#209dd7',
        lineWidth: 2,
        priceLineVisible: true,
        priceLineColor: '#209dd7',
        lastValueVisible: true,
      });

      chartRef.current = chart;
      seriesRef.current = series as ISeriesApi;

      // Handle resize
      ro = new ResizeObserver(entries => {
        for (const entry of entries) {
          if (chartRef.current && entry.contentRect) {
            chartRef.current.applyOptions({
              width: entry.contentRect.width,
              height: entry.contentRect.height,
            });
          }
        }
      });
      if (containerRef.current) {
        ro.observe(containerRef.current);
      }
    });

    return () => {
      ro?.disconnect();
      if (chart) {
        chart.remove();
        chartRef.current = null;
        seriesRef.current = null;
      }
    };
  }, []);

  // Update chart data when ticker changes or history updates
  useEffect(() => {
    if (!seriesRef.current || !selectedTicker) return;

    const history = priceHistory[selectedTicker] ?? [];
    if (history.length === 0) return;

    const tickerChanged = prevTickerRef.current !== selectedTicker;
    prevTickerRef.current = selectedTicker;

    const now = Math.floor(Date.now() / 1000);
    const intervalSec = 1; // approximate 1 second per data point

    const data = history.map((price, i) => ({
      time: (now - (history.length - 1 - i) * intervalSec) as unknown as import('lightweight-charts').Time,
      value: price,
    }));

    try {
      if (tickerChanged) {
        seriesRef.current.setData(data);
        chartRef.current?.timeScale().fitContent();
      } else {
        const lastPoint = data[data.length - 1];
        if (lastPoint) {
          seriesRef.current.update(lastPoint);
        }
      }
    } catch {
      try {
        seriesRef.current.setData(data);
      } catch {
        // ignore
      }
    }
  }, [selectedTicker, priceHistory]);

  const pd = selectedTicker ? prices[selectedTicker] : null;

  const formatPrice = (p: number) =>
    p < 10 ? p.toFixed(4) : p.toFixed(2);

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: '#0d1117', borderRight: '1px solid #30363d' }}
    >
      {/* Chart header */}
      <div
        className="px-4 py-2 border-b shrink-0 flex items-center justify-between"
        style={{ borderColor: '#30363d', height: '40px' }}
      >
        {selectedTicker ? (
          <>
            <div className="flex items-center gap-3">
              <span className="text-sm font-black" style={{ color: '#ecad0a' }}>
                {selectedTicker}
              </span>
              {pd && (
                <>
                  <span className="text-base font-bold" style={{ color: '#e6edf3' }}>
                    ${formatPrice(pd.price)}
                  </span>
                  <span
                    className="text-xs"
                    style={{
                      color: pd.price >= pd.previousPrice ? '#22c55e' : '#ef4444',
                    }}
                  >
                    {pd.price >= pd.previousPrice ? '▲' : '▼'}{' '}
                    {Math.abs(pd.price - pd.previousPrice).toFixed(3)}{' '}
                    ({(((pd.price - pd.previousPrice) / (pd.previousPrice || 1)) * 100).toFixed(3)}%)
                  </span>
                </>
              )}
            </div>
            <span className="text-xs" style={{ color: '#484f58' }}>
              PRICE CHART (session)
            </span>
          </>
        ) : (
          <span className="text-xs" style={{ color: '#484f58' }}>
            Select a ticker from the watchlist
          </span>
        )}
      </div>

      {/* Chart container */}
      <div className="flex-1 relative" ref={containerRef}>
        {!selectedTicker && (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center"
            style={{ color: '#30363d' }}
          >
            <div className="text-4xl mb-2">📈</div>
            <div className="text-sm">Click a ticker to view its chart</div>
          </div>
        )}
      </div>
    </div>
  );
}
