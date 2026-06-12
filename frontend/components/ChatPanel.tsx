'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { api, ChatResponse } from '@/lib/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  executedTrades?: Array<{ ticker: string; side: string; quantity: number; price: number }>;
  watchlistChanges?: Array<{ ticker: string; action: string }>;
  errors?: string[];
  timestamp: Date;
}

interface ChatPanelProps {
  onTradeSuccess?: () => void;
  onWatchlistUpdate?: () => void;
}

function TradeChip({ trade }: { trade: { ticker: string; side: string; quantity: number; price: number } }) {
  const isBuy = trade.side === 'buy';
  return (
    <div
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono"
      style={{
        background: isBuy ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
        border: `1px solid ${isBuy ? '#22c55e' : '#ef4444'}`,
        color: isBuy ? '#22c55e' : '#ef4444',
      }}
    >
      <span>{isBuy ? '▲' : '▼'}</span>
      <span>
        {trade.side.toUpperCase()} {trade.quantity} {trade.ticker} @ ${trade.price.toFixed(2)}
      </span>
    </div>
  );
}

export default function ChatPanel({ onTradeSuccess, onWatchlistUpdate }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        "Hello! I'm FinAlly, your AI trading assistant. I can analyze your portfolio, suggest trades, and execute them on your behalf. What would you like to know?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const response: ChatResponse = await api.sendChat(text);

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        executedTrades: response.trades_executed,
        watchlistChanges: response.watchlist_changes_executed,
        errors: response.errors,
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, assistantMsg]);

      if (response.trades_executed && response.trades_executed.length > 0) {
        onTradeSuccess?.();
      }
      if (response.watchlist_changes_executed && response.watchlist_changes_executed.length > 0) {
        onWatchlistUpdate?.();
      }
    } catch (err) {
      const errMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Sorry, I encountered an error: ${err instanceof Error ? err.message : 'Unknown error'}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, onTradeSuccess, onWatchlistUpdate]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatTime = (d: Date) =>
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });

  return (
    <div
      className="flex flex-col h-full"
      style={{
        background: '#1a1a2e',
        borderLeft: '1px solid #30363d',
      }}
    >
      {/* Header */}
      <div
        className="px-3 py-2 border-b shrink-0 flex items-center justify-between"
        style={{ borderColor: '#30363d' }}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold tracking-widest" style={{ color: '#8b949e' }}>
            AI ASSISTANT
          </span>
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{ background: 'rgba(32,157,215,0.15)', color: '#209dd7', fontSize: 9 }}
          >
            FinAlly
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
        {messages.map(msg => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className="max-w-full px-3 py-2 rounded text-xs leading-relaxed"
              style={{
                background:
                  msg.role === 'user'
                    ? 'rgba(117,57,145,0.25)'
                    : '#21262d',
                border: `1px solid ${msg.role === 'user' ? '#753991' : '#30363d'}`,
                color: '#e6edf3',
                wordBreak: 'break-word',
              }}
            >
              {msg.content}
            </div>

            {/* Executed trades chips */}
            {msg.executedTrades && msg.executedTrades.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1 max-w-full">
                {msg.executedTrades.map((trade, i) => (
                  <TradeChip key={i} trade={trade} />
                ))}
              </div>
            )}

            {/* Watchlist changes */}
            {msg.watchlistChanges && msg.watchlistChanges.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {msg.watchlistChanges.map((change, i) => (
                  <div
                    key={i}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs"
                    style={{
                      background: 'rgba(32,157,215,0.15)',
                      border: '1px solid #209dd7',
                      color: '#209dd7',
                    }}
                  >
                    {change.action === 'add' ? '+' : '-'} {change.ticker}
                  </div>
                ))}
              </div>
            )}

            {/* Errors */}
            {msg.errors && msg.errors.length > 0 && (
              <div className="mt-1">
                {msg.errors.map((err, i) => (
                  <div
                    key={i}
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      background: 'rgba(239,68,68,0.1)',
                      border: '1px solid rgba(239,68,68,0.3)',
                      color: '#ef4444',
                    }}
                  >
                    {err}
                  </div>
                ))}
              </div>
            )}

            <span className="text-xs mt-0.5" style={{ color: '#484f58', fontSize: 9 }}>
              {formatTime(msg.timestamp)}
            </span>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="flex items-start">
            <div
              className="px-3 py-2 rounded text-xs"
              style={{ background: '#21262d', border: '1px solid #30363d' }}
            >
              <div className="flex items-center gap-1.5" style={{ color: '#8b949e' }}>
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div
                      key={i}
                      className="w-1.5 h-1.5 rounded-full"
                      style={{
                        background: '#209dd7',
                        animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                      }}
                    />
                  ))}
                </div>
                <span>Thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div
        className="px-3 py-2 border-t shrink-0"
        style={{ borderColor: '#30363d' }}
      >
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask FinAlly... (Enter to send)"
            className="flex-1 px-2 py-1.5 text-xs rounded resize-none"
            style={{
              background: '#0d1117',
              border: '1px solid #30363d',
              color: '#e6edf3',
              outline: 'none',
              lineHeight: '1.4',
              minHeight: '36px',
              maxHeight: '80px',
            }}
            rows={1}
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="px-3 py-1 text-xs font-bold rounded self-end"
            style={{
              background:
                loading || !input.trim() ? '#21262d' : '#753991',
              color: loading || !input.trim() ? '#484f58' : '#fff',
              border: 'none',
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            SEND
          </button>
        </div>
        <div className="text-xs mt-1" style={{ color: '#30363d', fontSize: 9 }}>
          Shift+Enter for newline
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
