'use client';

import { useState, useEffect, useCallback } from 'react';
import { api, Portfolio, PortfolioSnapshot } from '@/lib/api';

export function usePortfolio(pollInterval = 5000) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getPortfolio();
      setPortfolio(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load portfolio');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, pollInterval);
    return () => clearInterval(interval);
  }, [refresh, pollInterval]);

  return { portfolio, loading, error, refresh };
}

export function usePortfolioHistory(pollInterval = 10000) {
  const [history, setHistory] = useState<PortfolioSnapshot[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getPortfolioHistory();
      setHistory(data.snapshots ?? []);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, pollInterval);
    return () => clearInterval(interval);
  }, [refresh, pollInterval]);

  return { history, loading, refresh };
}

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getWatchlist();
      setWatchlist((data.tickers ?? []).map(item => item.ticker));
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addTicker = useCallback(async (ticker: string) => {
    await api.addToWatchlist(ticker);
    await refresh();
  }, [refresh]);

  const removeTicker = useCallback(async (ticker: string) => {
    await api.removeFromWatchlist(ticker);
    await refresh();
  }, [refresh]);

  return { watchlist, loading, refresh, addTicker, removeTicker };
}
