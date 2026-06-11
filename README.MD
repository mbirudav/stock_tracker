# FinAlly — AI Trading Workstation

FinAlly (Finance Ally) is an AI-powered trading workstation that streams live market data, lets you trade a simulated portfolio, and ships with an LLM chat assistant that can analyze your positions and execute trades on your behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

> Capstone project for an agentic AI coding course — built end-to-end by orchestrated coding agents.

## Features

- **Live price streaming** via Server-Sent Events, with green/red flash animations and progressively-filling sparklines
- **Simulated trading** — market orders, instant fill, $10,000 starting cash, fractional shares
- **Portfolio analytics** — positions table, P&L heatmap (treemap), and a portfolio-value chart over time
- **AI assistant** — chat that analyzes your portfolio and auto-executes trades and watchlist changes through natural language
- **Watchlist management** — add/remove tickers manually or via the AI

## Tech Stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js + TypeScript (static export), Tailwind CSS |
| Backend | FastAPI (Python, managed with `uv`) |
| Database | SQLite (lazy-initialized, volume-mounted) |
| Real-time | Server-Sent Events (SSE) |
| AI | LiteLLM → OpenRouter (`openai/gpt-oss-120b` via Cerebras), structured outputs |
| Market data | Built-in GBM simulator (default) or Massive/Polygon API (optional) |
| Packaging | Single Docker container on port 8000 |

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env        # then add your OPENROUTER_API_KEY

# 2. Launch (builds image if needed, runs container, mounts the SQLite volume)
./scripts/start_mac.sh      # macOS / Linux
./scripts/start_windows.ps1 # Windows PowerShell

# 3. Open the app
open http://localhost:8000
```

Stop the container with `./scripts/stop_mac.sh` / `./scripts/stop_windows.ps1` (data persists across restarts).

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes (unless `LLM_MOCK=true`) | OpenRouter key for the AI chat assistant |
| `MASSIVE_API_KEY` | No | Enables real market data; omit to use the built-in simulator |
| `LLM_MOCK` | No | Set `true` for deterministic mock LLM responses (tests/dev) |

## Architecture

A single FastAPI process serves everything on **port 8000**: REST endpoints under `/api/*`, the live price stream at `/api/stream/prices`, and the exported Next.js frontend as static files. A background task drives an in-memory price cache (simulator or Massive poller) that the SSE stream reads from. State lives in a single SQLite file (`db/finally.db`), persisted via a Docker volume. Same origin throughout — no CORS, one port, one container.

## Project Structure

```
finally/
├── frontend/      # Next.js TypeScript app (static export)
├── backend/       # FastAPI uv project (API, SSE, market data, LLM, DB)
├── planning/      # Project documentation (PLAN.md is the source of truth)
├── scripts/       # start/stop scripts (macOS/Linux + Windows)
├── test/          # Playwright E2E tests
├── db/            # SQLite volume mount target
└── Dockerfile     # Multi-stage build (Node → Python)
```

See [`planning/PLAN.md`](planning/PLAN.md) for the full specification.
