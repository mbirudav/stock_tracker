// API utilities for FinAlly frontend

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pnl_pct: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  positions: Position[];
  recorded_at?: string;
}

export interface WatchlistItem {
  ticker: string;
  added_at?: string;
  price?: number | null;
  previous_price?: number | null;
  timestamp?: string | null;
  baseline_price?: number | null;
}

export interface WatchlistResponse {
  tickers: WatchlistItem[];
}

export interface PortfolioSnapshot {
  total_value: number;
  recorded_at: string;
}

export interface PortfolioHistoryResponse {
  snapshots: PortfolioSnapshot[];
}

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: 'buy' | 'sell';
}

export interface TradeResponse {
  success: boolean;
  trade?: {
    id?: string;
    ticker: string;
    side: string;
    quantity: number;
    price: number;
    executed_at: string;
  };
  portfolio?: Portfolio;
  error?: string;
}

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  actions?: {
    trades?: Array<{ ticker: string; side: string; quantity: number; price: number }>;
    watchlist_changes?: Array<{ ticker: string; action: string }>;
  };
  created_at?: string;
}

export interface ChatResponse {
  message: string;
  trades_executed?: Array<{ ticker: string; side: string; quantity: number; price: number }>;
  watchlist_changes_executed?: Array<{ ticker: string; action: string }>;
  errors?: string[];
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    // FastAPI errors come as {detail: ...}; detail may be a string or an
    // object like {success: false, error: "..."} (trade validation failures).
    const detail = body?.detail;
    let message: string;
    if (typeof detail === 'string') {
      message = detail;
    } else if (detail && typeof detail === 'object' && typeof detail.error === 'string') {
      message = detail.error;
    } else if (typeof body?.error === 'string') {
      message = body.error;
    } else {
      message = `HTTP ${response.status}`;
    }
    throw new Error(message);
  }

  return response.json();
}

export const api = {
  getPortfolio: () => apiFetch<Portfolio>('/api/portfolio'),
  getPortfolioHistory: () => apiFetch<PortfolioHistoryResponse>('/api/portfolio/history'),
  executeTrade: (trade: TradeRequest) =>
    apiFetch<TradeResponse>('/api/portfolio/trade', {
      method: 'POST',
      body: JSON.stringify(trade),
    }),
  getWatchlist: () => apiFetch<WatchlistResponse>('/api/watchlist'),
  addToWatchlist: (ticker: string) =>
    apiFetch<WatchlistItem>('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify({ ticker }),
    }),
  removeFromWatchlist: (ticker: string) =>
    apiFetch<void>(`/api/watchlist/${ticker}`, { method: 'DELETE' }),
  sendChat: (message: string) =>
    apiFetch<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
};
