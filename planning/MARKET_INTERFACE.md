# Market Data Interface — Unified Provider Design

> The single abstraction FinAlly's backend uses to get prices, regardless of source.
> Selection rule (PLAN §6): **`MASSIVE_API_KEY` set → Massive; otherwise → simulator.**
> Everything downstream (price cache, SSE stream, frontend) is source-agnostic.
>
> Companions: [`MASSIVE_api.md`](MASSIVE_api.md) (real-data source),
> [`MARKET_SIMULATOR.md`](MARKET_SIMULATOR.md) (simulated source).

---

## 1. Goals

1. **One interface, two implementations** — `SimulatorProvider` and `MassiveProvider`
   are interchangeable behind `MarketDataProvider`.
2. **Env-driven selection** — a factory reads `MASSIVE_API_KEY` and returns the right one.
3. **Pull model** — a single background task *pulls* quotes on a cadence the provider
   declares, writes them to an in-memory cache, and fans them out over SSE. Providers know
   nothing about caching, SSE, or the database.
4. **Source-agnostic semantics** — both providers return the same `Quote` shape carrying a
   current price **and** a daily baseline (`prev_close`) so "daily change %" works
   identically (resolves PLAN §13.1-#1).

---

## 2. Architecture

```
                         reads watchlist ∪ positions
                                   │
                        ┌──────────▼───────────┐     poll every provider.poll_interval
   MarketDataProvider ──►   MarketService      │◄──────────────────────────────────┐
   (Simulator | Massive)│   (background task)  │                                    │
                        └──────────┬───────────┘                                    │
                                   │ writes                                         │
                          ┌────────▼────────┐      ┌──────────────────┐             │
                          │   PriceCache    │─────►│  SSE subscribers │             │
                          │ {ticker: Tick}  │ push │  (asyncio.Queue) │             │
                          └─────────────────┘      └──────────────────┘             │
                                   │                                                │
                                   └── GET /api/portfolio, /api/watchlist ──────────┘
```

- **Provider** = swappable price source. Returns `Quote`s. Declares its own `poll_interval`.
- **MarketService** = owns the provider + cache, runs the poll loop, computes tick-over-tick
  `prev_price`, and publishes to SSE. The *only* component that touches both provider & cache.
- **PriceCache** = in-memory dict of the latest `PriceTick` per ticker. Survives nothing
  (rebuilt on boot); the DB holds durable state (positions, trades, snapshots).

---

## 3. Shared Types  (`backend/market/types.py`)

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

def utcnow() -> datetime:
    return datetime.now(timezone.utc)            # all timestamps UTC (PLAN §13.3-#1)

@dataclass(frozen=True, slots=True)
class Quote:
    """What a provider returns for one ticker, one poll."""
    ticker: str
    price: float            # latest price (trade/close/simulated)
    prev_close: float       # prior-session close — baseline for daily change %
    ts: datetime            # UTC time of this quote

@dataclass(frozen=True, slots=True)
class TickerInfo:
    """Result of validating/admitting a ticker into the universe."""
    ticker: str
    name: str
    seed_price: float       # a sane current price (simulator seeding / first display)
```

### PriceTick (cache entry) — `backend/market/cache.py`

```python
from dataclasses import dataclass

@dataclass(slots=True)
class PriceTick:
    ticker: str
    price: float
    prev_price: float       # previous *tick* — drives green/red flash direction
    prev_close: float       # daily baseline — drives "daily change %"
    ts: datetime

    @property
    def change(self) -> float:
        return self.price - self.prev_close

    @property
    def change_pct(self) -> float:
        return (self.price / self.prev_close - 1.0) * 100 if self.prev_close else 0.0

    @property
    def direction(self) -> str:
        if self.price > self.prev_price: return "up"
        if self.price < self.prev_price: return "down"
        return "flat"
```

> **Two "previous" values, deliberately distinct** (PLAN §13.4-#3): `prev_close` is the
> *daily* baseline (yesterday's close); `prev_price` is the *last tick*, used only to color
> the flash. The SSE payload sends `price` + `prev_close` (+ `ts`); the client derives
> direction as `sign(price − prev_price)` — but since the cache already tracks `prev_price`,
> the server can send `direction` too if preferred. Don't send all three redundantly.

---

## 4. The Interface  (`backend/market/provider.py`)

```python
from abc import ABC, abstractmethod
from collections.abc import Sequence
from .types import Quote, TickerInfo

class MarketDataProvider(ABC):
    """A swappable source of prices. Knows nothing about caching, SSE, or the DB."""

    name: str                       # "simulator" | "massive" — for logs/health
    poll_interval: float            # seconds between polls (provider decides cadence)

    @abstractmethod
    async def fetch_quotes(self, tickers: Sequence[str]) -> list[Quote]:
        """Return the current price + prev_close for each requested ticker.
        Called once per poll cycle by MarketService. Must not raise on a single
        bad ticker — skip it and return the rest."""

    @abstractmethod
    async def validate_ticker(self, ticker: str) -> TickerInfo | None:
        """Confirm `ticker` is priceable. Massive → /v3/reference/tickers.
        Simulator → always admit, minting a random seed price.
        Returns TickerInfo, or None if the symbol is unknown/un-priceable."""

    async def aclose(self) -> None:
        """Release resources (e.g. httpx client). Default: no-op."""
        return None
```

**Why `fetch_quotes` (pull) instead of a `stream()` generator?** A pull model maps cleanly
onto "poll every N seconds," keeps the simulator and the REST poller structurally identical,
and makes the cadence a property of the provider rather than buried in a loop. The simulator
simply advances its GBM one step per pull; Massive does one HTTP poll per pull.

---

## 5. Selection Factory  (`backend/market/__init__.py`)

```python
import os
from .provider import MarketDataProvider
from .simulator import SimulatorProvider
from .massive import MassiveProvider

def create_provider() -> MarketDataProvider:
    """PLAN §6 selection rule."""
    key = os.getenv("MASSIVE_API_KEY", "").strip()
    if key:
        return MassiveProvider(api_key=key)
    return SimulatorProvider()
```

A blank/whitespace `MASSIVE_API_KEY` counts as unset → simulator. Logged at startup:
`"market data source: simulator"` / `"... massive (tier=free|paid)"`.

---

## 6. MarketService — the poll loop  (`backend/market/service.py`)

```python
import asyncio, logging
from collections.abc import Callable
from .cache import PriceCache, PriceTick
from .provider import MarketDataProvider

log = logging.getLogger("market")

class MarketService:
    def __init__(self, provider: MarketDataProvider,
                 get_universe: Callable[[], list[str]]):
        self.provider = provider
        self.get_universe = get_universe        # () -> watchlist ∪ position tickers
        self.cache = PriceCache()
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="market-poll")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
        await self.provider.aclose()

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            tickers = self.get_universe()
            try:
                quotes = await self.provider.fetch_quotes(tickers)
                for q in quotes:
                    self.cache.update(q)         # computes prev_price internally
                await self._publish(self.cache.snapshot())
                backoff = 1.0
            except RateLimited:
                log.warning("rate limited; backing off %.1fs", backoff)
                await asyncio.sleep(backoff); backoff = min(backoff * 2, 60); continue
            except Exception:                    # never let the loop die
                log.exception("poll failed; serving cached prices")
            await asyncio.wait([self._stop.wait()], timeout=self.provider.poll_interval)

    # ---- SSE fan-out ----
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1)   # latest-wins
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _publish(self, ticks: list[PriceTick]) -> None:
        for q in list(self._subscribers):
            if q.full():
                q.get_nowait()                   # drop stale, keep newest
            q.put_nowait(ticks)
```

`PriceCache.update(quote)` sets `prev_price = existing.price` (or `quote.price` on first
sight), carries `prev_close` from the quote, and stamps `ts`.

---

## 7. How each provider satisfies the interface

| | `SimulatorProvider` | `MassiveProvider` |
|---|---|---|
| `poll_interval` | `0.5` s (smooth ticks) | paid `~3` s · free `0.5` s (hybrid) |
| `fetch_quotes` | advance GBM one step, return new prices | paid: `/v3/snapshot`; free: GBM-around-real-EOD anchor |
| `validate_ticker` | always admit + random seed | `/v3/reference/tickers`; `None` if unknown |
| `prev_close` source | per-ticker seed price | `session.previous_close` / `prevDay.c` |
| external deps | none | `httpx`, network |

Full simulator internals: [`MARKET_SIMULATOR.md`](MARKET_SIMULATOR.md).

### Massive provider strategy (resolves the free-tier reality)

```python
class MassiveProvider(MarketDataProvider):
    name = "massive"

    def __init__(self, api_key: str):
        self._key = api_key
        self._client = httpx.AsyncClient(
            base_url="https://api.polygon.io",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=10.0)
        self._tier: str | None = None             # detected on first poll
        self._anchors: dict[str, float] = {}      # free-tier: real EOD close per ticker
        self._sim: MarketSimulator | None = None  # free-tier: drift engine over anchors

    async def _detect_tier(self) -> str:
        r = await self._client.get("/v3/snapshot", params={"ticker.any_of": "AAPL"})
        self.poll_interval = 3.0 if r.is_success else 0.5
        return "paid" if r.is_success else "free"

    async def fetch_quotes(self, tickers):
        self._tier = self._tier or await self._detect_tier()
        if self._tier == "paid":
            return await self._snapshot(tickers)         # real-time
        return await self._hybrid(tickers)               # real anchor + simulated drift
```

- **Paid** → `/v3/snapshot?ticker.any_of=…` (≤250) → real `session.price` +
  `session.previous_close`. True live data.
- **Free** → fetch the real **previous close** once via **grouped daily** (one call for the
  whole universe; cache as the per-ticker *anchor* and `prev_close`), then on each pull
  apply small GBM drift around the anchor so the UI is lively and **anchored to real prices**.
  This honors "use real data when a key is set" within free-tier limits without a frozen UI.

> If you prefer strict honesty over liveliness on the free tier, make the hybrid optional via
> `MASSIVE_LIVE_DRIFT=false`, in which case free-tier prices are the static real EOD close.

---

## 8. The priced-ticker universe (resolves PLAN §13.1-#3)

`get_universe()` returns **watchlist ∪ position tickers**, deduplicated. Consequences:
- The poller always prices everything the user can see or hold — no position with a missing
  price (which would break P&L).
- When the LLM/user buys an unwatched ticker, the trade path **auto-adds it to the watchlist**
  (so it gets a streaming price) *after* `validate_ticker` succeeds.
- New tickers are seeded immediately via a one-shot `fetch_quotes([ticker])` + cache write so
  the UI isn't blank until the next poll.

### Unknown / newly-added tickers (PLAN §13.1-#2)
- **Massive:** `validate_ticker` → reject if reference API returns `count: 0`.
- **Simulator:** always admit; mint a random seed price (e.g. `uniform(20, 500)`), which also
  becomes `prev_close`.

---

## 9. SSE payload contract

Per connected client, on connect send a **snapshot** of all known ticks, then deltas each
poll. One event shape:

```json
{ "ticker": "AAPL", "price": 291.10, "prev_close": 290.55,
  "direction": "up", "ts": "2026-06-10T15:00:00.500Z" }
```

Sending `prev_close` lets the client compute daily change % immediately and gives late joiners
a baseline (PLAN §13.4-#4). `direction` is included since the cache already knows `prev_price`;
the client does not also need `prev_price`.

---

## 10. Testing

- **`MockProvider(MarketDataProvider)`** returns scripted `Quote`s — deterministic, offline,
  no network. Used by API/SSE unit tests and E2E (`LLM_MOCK=true` runs already avoid the LLM;
  this avoids the network too).
- **Simulator** with a fixed RNG seed → reproducible price paths (see
  [`MARKET_SIMULATOR.md`](MARKET_SIMULATOR.md) §Determinism).
- **MassiveProvider** tested against **recorded JSON fixtures** (the verified responses in
  `MASSIVE_api.md` §Appendix) via `httpx.MockTransport` — no live calls, no key needed in CI.
- **Interface conformance test** parametrized over every provider: `fetch_quotes` returns one
  `Quote` per known ticker, `prev_close > 0`, `ts` is tz-aware UTC.

---

## 11. Module layout

```
backend/market/
├── __init__.py        # create_provider() factory  (§5)
├── types.py           # Quote, TickerInfo, utcnow   (§3)
├── provider.py        # MarketDataProvider ABC      (§4)
├── cache.py           # PriceCache, PriceTick       (§3, §6)
├── service.py         # MarketService poll loop+SSE (§6)
├── simulator.py       # SimulatorProvider           (MARKET_SIMULATOR.md)
└── massive.py         # MassiveProvider             (§7, MASSIVE_api.md)
```

## 12. Lifecycle (FastAPI)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    provider = create_provider()
    app.state.market = MarketService(provider, get_universe=load_universe_from_db)
    await app.state.market.start()
    try:
        yield
    finally:
        await app.state.market.stop()
```

`/api/stream/prices` calls `market.subscribe()`; `/api/watchlist` & the trade path mutate the
DB (which `get_universe()` reads next poll) and trigger an immediate seed for new tickers.
