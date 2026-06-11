# Market Simulator — Approach & Code Structure

> FinAlly's **default** price source (PLAN §6): runs with **zero external dependencies**,
> no API key, no network. Produces realistic, lively, correlated price action via
> **Geometric Brownian Motion (GBM)** with a market factor and occasional shock events.
>
> Implements the `MarketDataProvider` interface from
> [`MARKET_INTERFACE.md`](MARKET_INTERFACE.md). Also reused as the *drift engine* for the
> Massive free-tier hybrid (see [`MASSIVE_api.md`](MASSIVE_api.md) §3).

---

## 1. Goals

| Requirement (PLAN §6) | How it's met |
|---|---|
| Realistic prices | Per-ticker seed prices + calibrated drift/volatility |
| ~500 ms updates | `poll_interval = 0.5`; one GBM step per pull |
| Correlated moves (tech moves together) | Shared **market factor** + per-ticker **beta** |
| Occasional drama (2–5% events) | Low-probability **jump** term per step |
| Self-contained | Pure Python `random` + `math`; no deps |
| Testable / deterministic | Seedable `random.Random` |
| Arbitrary new tickers | Random seed price on admit (PLAN §13.1-#2) |

---

## 2. The Math — discrete GBM

Standard GBM closed-form step over interval `Δt` (in years):

```
S(t+Δt) = S(t) · exp( (μ − ½σ²)·Δt  +  σ·√Δt·Z )
```

- `S` — price
- `μ` — annualized drift (expected return; small, e.g. 0.05–0.15)
- `σ` — annualized volatility (e.g. 0.20 stable … 0.80 meme stock)
- `Z` — standard-normal shock, `Z ~ N(0, 1)`
- `Δt` — time step in years

Properties that make GBM ideal here: prices stay **strictly positive**, returns are
log-normal, and the `−½σ²` correction keeps the expected drift unbiased.

### Time step (`Δt`)

Ticking every **0.5 s** of wall-clock against a **continuous (24/7) demo clock**:

```
SECONDS_PER_YEAR = 365 * 24 * 3600 = 31_557_600
dt = 0.5 / SECONDS_PER_YEAR ≈ 1.585e-8   (years per tick)
```

> `dt` is the single knob for "liveliness." Real `σ` over a real trading year gives subtle
> motion; for a punchy demo, **scale σ up** (or shrink `SECONDS_PER_YEAR`) so visible wiggle
> appears every few seconds. Defaults below are pre-exaggerated for demo feel.

---

## 3. Correlation — market factor + beta

Independent per-ticker shocks would look unrealistic (everything random-walks alone). Instead,
split each ticker's shock into a **common market component** and an **idiosyncratic** one:

```
Z_market         ~ N(0, 1)          # one draw shared by all tickers each step
Z_idio_i         ~ N(0, 1)          # per-ticker independent draw
Z_i = βᵢ · Z_market  +  √(1 − βᵢ²) · Z_idio_i
```

- `βᵢ ∈ [0, 1]` = how tightly ticker *i* tracks the market.
- High β (e.g. NVDA, TSLA ≈ 0.8) → tech moves together. Low β (e.g. JPM, V ≈ 0.4) →
  more independent. This construction keeps each `Z_i` unit-variance while injecting
  cross-ticker correlation ≈ `βᵢ·βⱼ`.

---

## 4. Shock events (drama)

Each ticker, each step, with small probability, gets an extra one-off jump of ±2–5%:

```
if rand() < EVENT_PROB:                         # e.g. 0.001 per ticker per tick
    jump = sign(rand) · uniform(0.02, 0.05)
    S *= (1 + jump)
```

`EVENT_PROB` is per-ticker-per-tick; at 0.5 s ticks, `0.001` ⇒ a given ticker jumps roughly
every ~8 minutes on average, so *something* on a 10-ticker board pops every ~50 s.

---

## 5. Seed prices & parameters

Default universe (PLAN §7). Seeds are illustrative "current" prices; they also serve as each
ticker's **`prev_close` baseline** for daily-change %. (Optionally refresh seeds at boot from
Massive **grouped daily** — one free call — so the sim starts at *real* recent prices.)

```python
# (seed_price, annualized_drift μ, annualized_vol σ, market_beta β)
SEED = {
    "AAPL": (290.0, 0.10, 0.28, 0.75),
    "GOOGL":(180.0, 0.11, 0.30, 0.72),
    "MSFT": (440.0, 0.10, 0.26, 0.74),
    "AMZN": (205.0, 0.12, 0.34, 0.70),
    "TSLA": (250.0, 0.05, 0.65, 0.82),   # high vol + high beta = dramatic
    "NVDA": (135.0, 0.18, 0.55, 0.85),
    "META": (560.0, 0.13, 0.38, 0.71),
    "JPM":  (215.0, 0.06, 0.22, 0.45),   # low beta = bank, more independent
    "V":    (290.0, 0.07, 0.20, 0.42),
    "NFLX": (700.0, 0.10, 0.40, 0.60),
}

EVENT_PROB       = 0.001          # per ticker, per tick
EVENT_MIN, EVENT_MAX = 0.02, 0.05 # ±2–5%
SECONDS_PER_YEAR = 31_557_600
TICK_SECONDS     = 0.5
```

### Unknown / newly-added tickers (PLAN §13.1-#2)
Admit any symbol; mint defaults: `seed = uniform(20, 500)`, `μ = 0.08`, `σ = 0.40`,
`β = 0.6`. The minted seed becomes that ticker's `prev_close`.

---

## 6. Code structure  (`backend/market/simulator.py`)

```python
from __future__ import annotations
import math, random
from collections.abc import Sequence
from dataclasses import dataclass, field

from .provider import MarketDataProvider
from .types import Quote, TickerInfo, utcnow

SECONDS_PER_YEAR = 31_557_600
TICK_SECONDS     = 0.5
EVENT_PROB       = 0.001
EVENT_MIN, EVENT_MAX = 0.02, 0.05

@dataclass(slots=True)
class _Sim:
    ticker: str
    price: float
    prev_close: float          # daily baseline (= initial seed)
    mu: float
    sigma: float
    beta: float

class MarketSimulator:
    """Pure price-path engine. No I/O. One `step()` == one Δt advance for all tickers."""

    def __init__(self, seeds: dict[str, tuple], *, rng: random.Random | None = None,
                 dt: float | None = None):
        self.rng = rng or random.Random()
        self.dt = dt if dt is not None else TICK_SECONDS / SECONDS_PER_YEAR
        self.sims: dict[str, _Sim] = {}
        for t, (p, mu, sig, beta) in seeds.items():
            self.sims[t] = _Sim(t, p, p, mu, sig, beta)

    def ensure(self, ticker: str) -> _Sim:
        """Admit an unknown ticker with random defaults (PLAN §13.1-#2)."""
        s = self.sims.get(ticker)
        if s is None:
            seed = round(self.rng.uniform(20, 500), 2)
            s = _Sim(ticker, seed, seed, mu=0.08, sigma=0.40, beta=0.6)
            self.sims[ticker] = s
        return s

    def step(self, tickers: Sequence[str]) -> list[Quote]:
        z_market = self.rng.gauss(0.0, 1.0)              # shared market shock
        sqrt_dt = math.sqrt(self.dt)
        out: list[Quote] = []
        for t in tickers:
            s = self.ensure(t)
            z = s.beta * z_market + math.sqrt(1 - s.beta**2) * self.rng.gauss(0, 1)
            drift = (s.mu - 0.5 * s.sigma**2) * self.dt
            shock = s.sigma * sqrt_dt * z
            s.price *= math.exp(drift + shock)
            if self.rng.random() < EVENT_PROB:           # occasional 2–5% jump
                jump = (1 if self.rng.random() < 0.5 else -1) * \
                       self.rng.uniform(EVENT_MIN, EVENT_MAX)
                s.price *= (1 + jump)
            s.price = max(s.price, 0.01)                 # GBM stays positive; guard anyway
            out.append(Quote(t, round(s.price, 2), s.prev_close, utcnow()))
        return out


class SimulatorProvider(MarketDataProvider):
    """Adapts MarketSimulator to the provider interface."""
    name = "simulator"
    poll_interval = TICK_SECONDS

    def __init__(self, seeds: dict[str, tuple] | None = None,
                 rng: random.Random | None = None):
        from .seeds import SEED                          # default universe table
        self._engine = MarketSimulator(seeds or SEED, rng=rng)

    async def fetch_quotes(self, tickers: Sequence[str]) -> list[Quote]:
        return self._engine.step(tickers)               # one GBM step, no I/O

    async def validate_ticker(self, ticker: str) -> TickerInfo | None:
        s = self._engine.ensure(ticker.upper())         # always admit
        return TickerInfo(s.ticker, s.ticker, s.price)
```

> `fetch_quotes` is `async` only to satisfy the interface — the simulator never awaits.
> `MarketService` calls it every `poll_interval` (0.5 s), so each call is exactly one Δt.

---

## 7. Determinism & testing

```python
sim = MarketSimulator(SEED, rng=random.Random(42))      # fixed seed → fixed path
a = sim.step(["AAPL"]); b = sim.step(["AAPL"])
# Re-running with Random(42) reproduces a, b exactly.
```

- **Reproducible paths** for unit tests (assert exact prices) and snapshot/regression tests.
- **Statistical tests:** over N steps, realized mean log-return ≈ `(μ−½σ²)·dt·N` and realized
  vol ≈ `σ·√(dt·N)` within tolerance — validates the GBM math (PLAN §12).
- **Correlation test:** with high β, `corr(returns_i, returns_j)` over many steps is clearly
  positive; with β≈0 it's ≈0.
- **Positivity invariant:** price never ≤ 0 across a long run.
- **Determinism in E2E:** pass a fixed-seed RNG so the watchlist shows stable values.

---

## 8. Tuning guide

| Want… | Change |
|------|--------|
| More visible motion | ↑ `σ`, or ↓ `SECONDS_PER_YEAR` (bigger `dt`) |
| Calmer board | ↓ `σ`, ↓ `EVENT_PROB` |
| More/bigger drama | ↑ `EVENT_PROB`, widen `EVENT_MIN/MAX` |
| Tighter sector coupling | ↑ `β` across tech names |
| Upward-trending demo | ↑ `μ` (note: drift is tiny per tick; vol dominates short-term) |
| Start at real prices | Seed from Massive **grouped daily** at boot (one free call) |

---

## 9. Integration recap

- Implements `MarketDataProvider`; selected by `create_provider()` when `MASSIVE_API_KEY`
  is unset (`MARKET_INTERFACE.md` §5).
- `MarketService` pulls `fetch_quotes` every 0.5 s → cache → SSE. The simulator supplies both
  the current `price` and the `prev_close` baseline, so the rest of the system can't tell it
  from real data (`MARKET_INTERFACE.md` §3, §9).
- The same `MarketSimulator` engine animates the **Massive free-tier hybrid**, driven around
  real EOD anchors instead of seed prices (`MASSIVE_api.md` §3).

### Module layout
```
backend/market/
├── simulator.py    # MarketSimulator + SimulatorProvider  (this doc)
└── seeds.py        # SEED table (§5)
```
