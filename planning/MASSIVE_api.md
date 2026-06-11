# Massive (formerly Polygon.io) — Market Data API Reference

> Research reference for FinAlly's optional real-market-data path. Every endpoint
> marked **✅ verified** below was tested live on 2026-06-10 with the project's
> `MASSIVE_API_KEY` (a **free-tier** key). Paid-only endpoints are documented from
> the official docs and marked accordingly.

---

## 1. Overview

**Massive** is the rebrand of **Polygon.io** (announced **2025-10-30**). It is a REST +
WebSocket market-data provider for stocks, options, forex, crypto, and indices.

| Item | Value |
|------|-------|
| New base URL | `https://api.massive.com` |
| Legacy base URL | `https://api.polygon.io` *(still works; redirects/aliases the new one)* |
| Docs | `https://massive.com/docs/rest/...` (old `polygon.io/docs/...` 301-redirects here) |
| Pricing / tiers | `https://massive.com/pricing` |
| Official Python SDK | `massive` on PyPI (`pip install -U massive`; was `polygon-api-client`) |

> **FinAlly uses the legacy `api.polygon.io` host** in examples because it is what the
> free-tier key was validated against and it remains fully supported. Swapping to
> `api.massive.com` is a one-line base-URL change.

---

## 2. Authentication

Two equivalent methods — pick one:

```bash
# A) Query parameter
curl "https://api.polygon.io/v2/aggs/ticker/AAPL/prev?adjusted=true&apiKey=YOUR_KEY"

# B) Bearer header (preferred for code — keeps the key out of URLs/logs)
curl -H "Authorization: Bearer YOUR_KEY" \
     "https://api.polygon.io/v2/aggs/ticker/AAPL/prev?adjusted=true"
```

The key is read from `MASSIVE_API_KEY` in `.env`. Never log the URL with `apiKey=` in it.

---

## 3. Tiers & Rate Limits — **the decisive constraint**

| | Free (the project key) | Paid (Starter / Developer+) |
|---|---|---|
| Request limit | **5 requests / minute** | Unlimited |
| Data freshness | **End-of-day only** | 15-min delayed → real-time |
| Real-time snapshots | ❌ `NOT_AUTHORIZED` | ✅ |
| Last trade / quote | ❌ | ✅ |
| WebSocket streaming | ❌ | ✅ |

### Verified free-tier access matrix

| Endpoint | Free tier | Notes |
|----------|:---:|-------|
| `GET /v2/aggs/ticker/{t}/prev` | ✅ | Previous session OHLCV |
| `GET /v2/aggs/grouped/locale/us/market/stocks/{date}` | ✅ | **All ~12,000 tickers in ONE call** |
| `GET /v1/open-close/{t}/{date}` | ✅ | Daily O/H/L/C + pre/after-hours |
| `GET /v2/aggs/ticker/{t}/range/...` | ✅ | Historical bars (for the main chart) |
| `GET /v3/reference/tickers` | ✅ | Ticker validation / metadata |
| `GET /v2/snapshot/.../tickers[/{t}]` | ❌ | Real-time snapshot — paid |
| `GET /v3/snapshot` | ❌ | Universal snapshot — paid |
| `GET /v2/last/trade/{t}` | ❌ | Real-time last trade — paid |

> **Implication for FinAlly:** a *free* Massive key **cannot stream live prices.** It can
> only fetch real **end-of-day** prices. This is why the **simulator remains the default**
> (PLAN §6) and why the Massive provider on a free key should use a *hybrid* strategy:
> anchor to real EOD prices, then animate them with simulated drift. See
> [`MARKET_INTERFACE.md`](MARKET_INTERFACE.md) §"Massive provider strategy".

---

## 4. Field codes (OHLCV shorthand)

Aggregate/bar endpoints (`prev`, `grouped`, `range`) use single-letter keys:

| Key | Meaning | Key | Meaning |
|-----|---------|-----|---------|
| `T` | Ticker | `c` | Close price |
| `o` | Open price | `v` | Volume |
| `h` | High price | `vw` | Volume-weighted avg price |
| `l` | Low price | `n` | Number of transactions |
| `t` | Timestamp — **Unix milliseconds** (start of the bar) | | |

> ⚠️ **Timestamp units differ by endpoint.** Aggregates use **milliseconds**; snapshot
> `updated` and `lastTrade.t` use **nanoseconds**. `open-close` uses date strings only.

---

## 5. End-of-Day & Historical Endpoints (free-tier ✅)

### 5.1 Previous Close — `GET /v2/aggs/ticker/{ticker}/prev`

Latest completed session for one ticker. Good for a daily-baseline (`prev_close`).

```bash
curl "https://api.polygon.io/v2/aggs/ticker/AAPL/prev?adjusted=true&apiKey=YOUR_KEY"
```
**✅ Verified response:**
```json
{
  "ticker": "AAPL", "queryCount": 1, "resultsCount": 1, "adjusted": true,
  "results": [
    {"T":"AAPL","v":70108847,"vw":292.0338,"o":300.275,"c":290.55,
     "h":300.75,"l":287.78,"t":1781035200000,"n":1334123}
  ],
  "status": "OK", "request_id": "…", "count": 1
}
```

### 5.2 Grouped Daily — `GET /v2/aggs/grouped/locale/us/market/stocks/{date}`

**The most efficient free-tier call:** one request returns the whole US equity universe
for `{date}` (YYYY-MM-DD). Verified: **12,262 results in a single response.** Filter to the
watchlist client-side. Ideal for seeding/refreshing many tickers within the 5-req/min cap.

```bash
curl "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/2026-06-09?adjusted=true&apiKey=YOUR_KEY"
```
**✅ Verified response (truncated):**
```json
{
  "queryCount": 12262, "resultsCount": 12262, "adjusted": true,
  "results": [
    {"T":"HLNE","v":1436308,"vw":80.5723,"o":79.955,"c":80,"h":83.73,"l":79.64,"t":1781035200000,"n":21807},
    {"T":"CATX","v":1491131,"vw":2.9342,"o":2.96,"c":3,"h":3.04,"l":2.85,"t":1781035200000,"n":12100}
    // … one object per US ticker
  ]
}
```
> Pass the **most recent trading day**. Weekends/holidays return an empty `results`. A
> robust client walks back up to ~4 days to find the last session with data.

### 5.3 Daily Open/Close — `GET /v1/open-close/{ticker}/{date}`

Single ticker, single day, with pre/after-hours.

```bash
curl "https://api.polygon.io/v1/open-close/AAPL/2026-06-09?adjusted=true&apiKey=YOUR_KEY"
```
**✅ Verified response:**
```json
{"status":"OK","from":"2026-06-09","symbol":"AAPL","open":300.275,
 "high":300.75,"low":287.78,"close":290.55,"volume":70108847,
 "afterHours":291.11,"preMarket":300.8}
```

### 5.4 Aggregate Bars — `GET /v2/aggs/ticker/{ticker}/range/{mult}/{timespan}/{from}/{to}`

Historical OHLCV bars — backs the **main detail chart**. `timespan` ∈
`minute|hour|day|week|month`; `sort=asc|desc`; `limit` up to 50000.

```bash
curl "https://api.polygon.io/v2/aggs/ticker/AAPL/range/1/day/2026-06-01/2026-06-09?adjusted=true&sort=asc&apiKey=YOUR_KEY"
```
**✅ Verified response (truncated):**
```json
{"ticker":"AAPL","queryCount":7,"resultsCount":7,"adjusted":true,
 "results":[
   {"v":48849933,"vw":307.4113,"o":309.625,"c":306.31,"h":310.94,"l":305.02,"t":1780286400000,"n":904768},
   {"v":44534716,"vw":313.1982,"o":307.46,"c":315.2,"h":315.45,"l":306.685,"t":1780372800000,"n":821440}
 ]}
```

### 5.5 Ticker Reference / Validation — `GET /v3/reference/tickers`

Confirm a symbol exists & is active **before** adding it to the watchlist.

```bash
curl "https://api.polygon.io/v3/reference/tickers?ticker=AAPL&active=true&limit=1&apiKey=YOUR_KEY"
```
**✅ Verified response (truncated):**
```json
{"results":[{"ticker":"AAPL","name":"Apple Inc.","market":"stocks","locale":"us",
  "primary_exchange":"XNAS","type":"CS","active":true,"currency_name":"usd"}],
 "status":"OK","count":1}
```
> `count: 0` / empty `results` ⇒ unknown ticker → reject the add (or fall back to a random
> seed price per PLAN §13.1-#2).

---

## 6. Real-Time Endpoints (paid-only ❌ on free key)

Documented for the paid path. **All three return `NOT_AUTHORIZED` on the free key** —
verified.

### 6.1 Universal Snapshot v3 (recommended real-time) — `GET /v3/snapshot`

Modern, multi-asset. `ticker.any_of` accepts **up to 250** comma-separated tickers.

```bash
curl "https://api.polygon.io/v3/snapshot?ticker.any_of=AAPL,MSFT,NVDA&apiKey=YOUR_KEY"
```
**Response schema (from docs):**
```json
{
  "request_id": "…", "status": "OK",
  "results": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "market_status": "open",          // open | closed | early_trading | late_trading
      "session": {
        "price": 291.10,                 // ← current price
        "change": 0.55, "change_percent": 0.19,
        "open": 290.5, "high": 292.0, "low": 289.9,
        "close": 291.10, "previous_close": 290.55,   // ← daily baseline
        "volume": 51234567
      },
      "last_trade": {"price": 291.10, "size": 100, "exchange": 11, "conditions": [12]},
      "last_quote": {"bid": 291.08, "ask": 291.12, "bid_size": 3, "ask_size": 5, "timeframe": "REAL-TIME"}
    }
  ]
}
```
For FinAlly this is the cleanest real-time source: `session.price` = current,
`session.previous_close` = daily baseline — exactly the two numbers the cache needs.

### 6.2 Snapshot — All / Multiple Tickers (v2) — `GET /v2/snapshot/locale/us/markets/stocks/tickers`

Older but widely used. Add `?tickers=AAPL,MSFT` to limit; omit for the whole market.
Single ticker: `…/tickers/{ticker}`.

```json
{
  "status": "OK", "count": 1,
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 0.55, "todaysChangePerc": 0.19,
      "updated": 1781045123000000000,        // ⚠ NANOSECONDS
      "day":     {"o":290.5,"h":292.0,"l":289.9,"c":291.1,"v":51234567,"vw":291.0},
      "min":     {"o":291.0,"h":291.2,"l":290.9,"c":291.1,"v":12000,"vw":291.05,"av":51234567,"t":1781045100000},
      "prevDay": {"o":300.275,"h":300.75,"l":287.78,"c":290.55,"v":70108847,"vw":292.03},
      "lastTrade":{"p":291.10,"s":100,"x":11,"t":1781045123000000000,"c":[12],"i":"xyz"},
      "lastQuote":{"P":291.12,"S":5,"p":291.08,"s":3,"t":1781045123000000000}
    }
  ]
}
```
Field notes — `lastTrade`: `p`=price, `s`=size, `x`=exchange, `c`=conditions, `i`=id.
`lastQuote`: `P`/`S`=ask price/size, `p`/`s`=bid price/size. `min.av`=accumulated day volume.

### 6.3 Last Trade — `GET /v2/last/trade/{ticker}`
Single most-recent trade; paid. `{"results":{"p":291.10,"s":100,"t":…ns,"x":11,...}}`.

### 6.4 WebSocket (true streaming, paid)
`wss://socket.polygon.io/stocks` (or `socket.massive.com`). Auth → subscribe to
`T.AAPL` (trades), `Q.AAPL` (quotes), `A.AAPL` (per-second aggs).
**FinAlly uses REST polling, not WebSocket** (PLAN §6) — listed for completeness.

---

## 7. Python Usage

### 7.1 Raw `httpx` (recommended for FinAlly's async poller)

Minimal deps, fully async, trivial to mock in tests. This is the basis of `MassiveProvider`
in [`MARKET_INTERFACE.md`](MARKET_INTERFACE.md).

```python
import httpx

BASE = "https://api.polygon.io"

async def previous_close(client: httpx.AsyncClient, ticker: str, key: str) -> dict:
    r = await client.get(f"{BASE}/v2/aggs/ticker/{ticker}/prev",
                         params={"adjusted": "true"},
                         headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    return r.json()["results"][0]      # {"T","o","h","l","c","v","vw","t","n"}

async def grouped_daily(client: httpx.AsyncClient, date: str, key: str) -> dict[str, float]:
    """One call → {ticker: close} for the whole US market on `date`."""
    r = await client.get(
        f"{BASE}/v2/aggs/grouped/locale/us/market/stocks/{date}",
        params={"adjusted": "true"},
        headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    return {row["T"]: row["c"] for row in r.json().get("results", [])}
```

### 7.2 Official `massive` SDK (alternative)

```python
from massive import RESTClient            # pip install -U massive
client = RESTClient("YOUR_KEY")           # defaults to api.massive.com

prev = client.get_previous_close_agg("AAPL")          # paid/free: prev close
for bar in client.list_aggs("AAPL", 1, "day", "2026-06-01", "2026-06-09"):
    ...                                                # historical bars
# snapshots (paid): client.get_snapshot_all("stocks", ["AAPL","MSFT"])
```
> The SDK pulls in extra dependencies and is sync-first. For a single, well-understood set
> of endpoints inside an async background task, **raw `httpx` is preferred**; the SDK is a
> fine fallback if you want typed models out of the box.

---

## 8. Error Handling

| Symptom | Cause | Handling |
|---------|-------|----------|
| `{"status":"NOT_AUTHORIZED",...}` (HTTP 200/403) | Endpoint needs a paid tier | Detect at startup; fall back to EOD/hybrid path |
| HTTP `429` | >5 req/min on free tier | Exponential backoff; widen poll interval |
| Empty `results` on grouped/agg | Weekend/holiday/no data | Walk back up to ~4 days to last session |
| `count: 0` on reference | Unknown ticker | Reject add or assign random seed |
| HTTP `5xx` | Transient | Retry with jitter; keep serving cached prices |

> **Tier detection trick (used by `MassiveProvider`):** on startup, probe
> `GET /v3/snapshot?ticker.any_of=AAPL`. `NOT_AUTHORIZED` ⇒ free tier (EOD/hybrid mode);
> `OK` ⇒ paid (real-time snapshot polling).

---

## 9. Summary for FinAlly

- **Base/auth:** `api.polygon.io` (legacy, validated) or `api.massive.com`; Bearer header.
- **Free key reality:** EOD only, 5 req/min, no live snapshots. Best multi-ticker call is
  **grouped daily** (whole market in one request).
- **Paid key:** poll **`/v3/snapshot`** every few seconds for true live prices.
- **Validation:** `/v3/reference/tickers` gates watchlist adds.
- **History (main chart):** `/v2/aggs/.../range/...`.
- **Design consequence:** simulator stays the default; the Massive provider detects its tier
  and uses real-time snapshots (paid) or a real-EOD-anchored hybrid (free). Continues in
  [`MARKET_INTERFACE.md`](MARKET_INTERFACE.md).

### Appendix — verified test log (2026-06-10, free key)
| Call | Result |
|------|--------|
| `/v2/aggs/ticker/AAPL/prev` | ✅ OK — AAPL c=290.55 |
| `/v2/aggs/grouped/.../2026-06-09` | ✅ OK — 12,262 tickers |
| `/v1/open-close/AAPL/2026-06-09` | ✅ OK — incl. pre/after-hours |
| `/v2/aggs/ticker/AAPL/range/1/day/...` | ✅ OK — 7 daily bars |
| `/v3/reference/tickers?ticker=AAPL` | ✅ OK — Apple Inc. |
| `/v2/snapshot/.../tickers/AAPL` | ❌ NOT_AUTHORIZED |
| `/v2/snapshot/.../tickers?tickers=AAPL,MSFT` | ❌ NOT_AUTHORIZED |
| `/v3/snapshot?ticker.any_of=AAPL,MSFT` | ❌ NOT_AUTHORIZED |
| `/v2/last/trade/AAPL` | ❌ NOT_AUTHORIZED |
