'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected';

export interface PriceData {
  price: number;
  previousPrice: number;
  timestamp: string;
}

export interface MarketDataState {
  prices: Record<string, PriceData>;
  priceHistory: Record<string, number[]>;
  connectionStatus: ConnectionStatus;
  flashingTickers: Record<string, 'up' | 'down'>;
}

interface PriceEventPayload {
  ticker: string;
  price: number;
  previous_price?: number;
  previousPrice?: number;
  timestamp: string;
  baseline_price?: number;
}

const HISTORY_MAX = 100;
const FLASH_DURATION = 500;

export function useMarketData(): MarketDataState {
  const [prices, setPrices] = useState<Record<string, PriceData>>({});
  const [priceHistory, setPriceHistory] = useState<Record<string, number[]>>({});
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [flashingTickers, setFlashingTickers] = useState<Record<string, 'up' | 'down'>>({});

  const flashTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearFlash = useCallback((ticker: string) => {
    setFlashingTickers(prev => {
      const next = { ...prev };
      delete next[ticker];
      return next;
    });
  }, []);

  const applyUpdate = useCallback(
    (data: PriceEventPayload, flash: boolean) => {
      const ticker = data.ticker;
      const price = data.price;
      const previousPrice = data.previous_price ?? data.previousPrice ?? price;
      const timestamp = data.timestamp;

      setPrices(prev => ({
        ...prev,
        [ticker]: { price, previousPrice, timestamp },
      }));

      setPriceHistory(prev => {
        const existing = prev[ticker] ?? [];
        const updated = [...existing, price];
        if (updated.length > HISTORY_MAX) {
          updated.splice(0, updated.length - HISTORY_MAX);
        }
        return { ...prev, [ticker]: updated };
      });

      if (flash) {
        const direction = price >= previousPrice ? 'up' : 'down';
        setFlashingTickers(prev => ({ ...prev, [ticker]: direction }));

        if (flashTimersRef.current[ticker]) {
          clearTimeout(flashTimersRef.current[ticker]);
        }
        flashTimersRef.current[ticker] = setTimeout(() => {
          clearFlash(ticker);
        }, FLASH_DURATION);
      }
    },
    [clearFlash]
  );

  const connect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
    }

    setConnectionStatus('reconnecting');

    const es = new EventSource('/api/stream/prices');
    esRef.current = es;

    es.onopen = () => {
      setConnectionStatus('connected');
    };

    // The backend sends NAMED events: 'snapshot' (once on connect, an array
    // of all current prices) and 'price' (one object per ticker per tick).
    // Named events do NOT fire es.onmessage — must use addEventListener.
    es.addEventListener('snapshot', (event: MessageEvent) => {
      try {
        const items: PriceEventPayload[] = JSON.parse(event.data);
        if (Array.isArray(items)) {
          items.forEach(item => applyUpdate(item, false));
        }
      } catch {
        // ignore parse errors
      }
    });

    es.addEventListener('price', (event: MessageEvent) => {
      try {
        const data: PriceEventPayload = JSON.parse(event.data);
        applyUpdate(data, true);
      } catch {
        // ignore parse errors
      }
    });

    es.onerror = () => {
      setConnectionStatus('disconnected');
      es.close();
      esRef.current = null;

      // Attempt reconnect after 3 seconds
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, 3000);
    };
  }, [applyUpdate]);

  useEffect(() => {
    connect();

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      Object.values(flashTimersRef.current).forEach(clearTimeout);
    };
  }, [connect]);

  return { prices, priceHistory, connectionStatus, flashingTickers };
}
