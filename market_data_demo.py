#!/usr/bin/env python3
"""
FinAlly — Live Market Data Terminal Demo

A self-contained terminal dashboard driven by the backend market data layer
(MarketDataSimulator behind UnifiedMarketData). No network or API keys needed.

What you see:
  - A scrolling ticker tape across the top
  - A live quote table (price, change, bid/ask, volume) with a sparkline
    graph for every ticker
  - A large detailed price chart that rotates through each ticker

Usage:
    python market_data_demo.py                      # default watchlist
    python market_data_demo.py AAPL TSLA BTC        # custom symbols
    python market_data_demo.py --refresh 0.5        # faster updates
    python market_data_demo.py --rotate 5           # chart rotation seconds
    python market_data_demo.py --ticks 20           # run 20 frames then exit

Press Ctrl+C to quit.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
from collections import deque
from typing import Deque, Dict, List, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import (
    Interval,
    MarketDataSimulator,
    Period,
    Quote,
    UnifiedMarketData,
)

DEFAULT_SYMBOLS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"]

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
WHITE = "\x1b[97m"
GREEN = "\x1b[32m"
BR_GREEN = "\x1b[92m"
RED = "\x1b[31m"
BR_RED = "\x1b[91m"
YELLOW = "\x1b[38;5;214m"   # FinAlly accent yellow (#ecad0a)
BLUE = "\x1b[38;5;38m"      # FinAlly primary blue (#209dd7)
GRAY = "\x1b[38;5;245m"

ALT_SCREEN_ON = "\x1b[?1049h\x1b[?25l"
ALT_SCREEN_OFF = "\x1b[?1049l\x1b[?25h"
HOME = "\x1b[H"
CLEAR_EOL = "\x1b[K"
CLEAR_BELOW = "\x1b[J"

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

SPARK_CHARS = "▁▂▃▄▅▆▇█"


def visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def clip(s: str, width: int) -> str:
    """Truncate *s* to *width* visible characters, preserving ANSI codes."""
    out: List[str] = []
    n = i = 0
    while i < len(s) and n < width:
        m = _ANSI_RE.match(s, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        out.append(s[i])
        i += 1
        n += 1
    out.append(RESET)
    return "".join(out)


def enable_ansi() -> None:
    if os.name == "nt":
        os.system("")  # activates VT processing in the Windows console


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def human_volume(v: int) -> str:
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    return str(v)


def trend_color(delta: float, bright: bool = False) -> str:
    if delta > 0:
        return BR_GREEN if bright else GREEN
    if delta < 0:
        return BR_RED if bright else RED
    return GRAY


def sparkline(values: Sequence[float], width: int) -> str:
    pts = list(values)[-width:]
    if not pts:
        return ""
    lo, hi = min(pts), max(pts)
    if hi - lo < 1e-9:
        body = "▄" * len(pts)
    else:
        body = "".join(
            SPARK_CHARS[min(7, int((v - lo) / (hi - lo) * 8))] for v in pts
        )
    return trend_color(pts[-1] - pts[0]) + body + RESET


# ---------------------------------------------------------------------------
# Big chart rendering
# ---------------------------------------------------------------------------

def render_chart(prices: Sequence[float], width: int, height: int) -> List[str]:
    """Render a line chart of *prices* as a list of *height* strings."""
    gutter = 11  # "  1234.56 ┤"
    plot_w = max(10, width - gutter)
    pts = list(prices)[-plot_w:]
    if len(pts) < 2:
        return [" " * width] * height

    lo, hi = min(pts), max(pts)
    if hi - lo < 1e-9:
        hi = lo + max(abs(lo) * 0.001, 0.01)
    span = hi - lo
    ys = [round((hi - p) / span * (height - 1)) for p in pts]

    grid = [[" "] * plot_w for _ in range(height)]
    grid[ys[0]][0] = "─"
    for x in range(1, len(pts)):
        y0, y1 = ys[x - 1], ys[x]
        if y0 == y1:
            grid[y1][x] = "─"
        elif y1 < y0:  # price moved up
            grid[y0][x] = "╯"
            grid[y1][x] = "╭"
            for y in range(y1 + 1, y0):
                grid[y][x] = "│"
        else:          # price moved down
            grid[y0][x] = "╮"
            grid[y1][x] = "╰"
            for y in range(y0 + 1, y1):
                grid[y][x] = "│"

    color = trend_color(pts[-1] - pts[0])
    mid_row = (height - 1) // 2
    lines: List[str] = []
    for row in range(height):
        if row == 0:
            label = f"{hi:>9.2f} ┤"
        elif row == height - 1:
            label = f"{lo:>9.2f} ┤"
        elif row == mid_row:
            label = f"{(hi + lo) / 2:>9.2f} ┤"
        else:
            label = " " * 9 + " ┤"
        lines.append(DIM + label + RESET + color + "".join(grid[row]) + RESET)
    return lines


# ---------------------------------------------------------------------------
# Ticker tape
# ---------------------------------------------------------------------------

def build_tape(symbols: Sequence[str], quotes: Dict[str, Quote]) -> List[Tuple[str, str]]:
    """Return the tape as a list of (char, color) cells so it can be sliced."""
    cells: List[Tuple[str, str]] = []
    for sym in symbols:
        q = quotes[sym]
        col = trend_color(q.change)
        arrow = "▲" if q.change >= 0 else "▼"
        for ch in f"  {sym} ":
            cells.append((ch, BOLD + WHITE))
        for ch in f"{q.price:,.2f} {arrow}{abs(q.change_percent):.2f}%":
            cells.append((ch, col))
        for ch in "  │":
            cells.append((ch, GRAY))
    return cells


def render_tape(cells: List[Tuple[str, str]], offset: int, width: int) -> str:
    if not cells:
        return ""
    doubled = cells + cells
    start = offset % len(cells)
    window = doubled[start:start + width]
    out: List[str] = []
    last_color = None
    for ch, col in window:
        if col != last_color:
            out.append(RESET + col)
            last_color = col
        out.append(ch)
    out.append(RESET)
    return "".join(out)


# ---------------------------------------------------------------------------
# Quote table
# ---------------------------------------------------------------------------

def render_table(
    symbols: Sequence[str],
    quotes: Dict[str, Quote],
    history: Dict[str, Deque[float]],
    tick_dir: Dict[str, float],
    focus: str,
    width: int,
) -> List[str]:
    spark_w = max(12, min(28, width - 76))
    header = (
        f"  {'SYMBOL':<9}{'PRICE':>10}  {'CHG':>8}  {'CHG%':>8}"
        f"  {'BID':>9}  {'ASK':>9}  {'VOL':>7}   TREND"
    )
    lines = [BOLD + BLUE + header + RESET]
    for sym in symbols:
        q = quotes[sym]
        d = tick_dir.get(sym, 0.0)
        arrow = "▲" if d > 0 else ("▼" if d < 0 else " ")
        price_col = trend_color(d, bright=True) if d else WHITE
        chg_col = trend_color(q.change)
        marker = YELLOW + "▶" + RESET if sym == focus else " "
        row = (
            f"{marker} "
            + BOLD + WHITE + f"{sym:<7}" + RESET
            + price_col + f"{arrow} " + f"{q.price:>9,.2f}" + RESET
            + chg_col + f"  {q.change:>+8.2f}  {q.change_percent:>+7.2f}%" + RESET
            + DIM + f"  {q.bid:>9,.2f}  {q.ask:>9,.2f}  {human_volume(q.volume):>7}" + RESET
            + "   " + sparkline(history[sym], spark_w)
        )
        lines.append(row)
    return lines


# ---------------------------------------------------------------------------
# History pre-fill
# ---------------------------------------------------------------------------

def prefill_history(
    sim: MarketDataSimulator, umd: UnifiedMarketData, symbol: str, points: int
) -> List[float]:
    """Seed the chart with intraday history, rescaled to join the live price."""
    bars = sim.get_historical(symbol, period=Period.DAY_1, interval=Interval.MINUTE_5)
    closes = [b.close for b in bars][-points:]
    live = umd.get_quote(symbol, use_cache=False).price
    if closes and closes[-1] > 0:
        scale = live / closes[-1]
        closes = [c * scale for c in closes]
    closes.append(live)
    return closes


# ---------------------------------------------------------------------------
# Frame rendering
# ---------------------------------------------------------------------------

def render_frame(
    symbols: Sequence[str],
    quotes: Dict[str, Quote],
    history: Dict[str, Deque[float]],
    tick_dir: Dict[str, float],
    umd: UnifiedMarketData,
    sim: MarketDataSimulator,
    focus: str,
    tape_offset: int,
    tick: int,
    rotate_secs: float,
) -> str:
    cols, rows = shutil.get_terminal_size((110, 34))
    width = max(60, cols)
    rule = GRAY + "─" * width + RESET

    lines: List[str] = []

    # Header
    status = umd.get_market_status().value.replace("_", " ").upper()
    clock = time.strftime("%H:%M:%S")
    left = YELLOW + BOLD + " FinAlly " + RESET + GRAY + "· Market Data Demo" + RESET
    right = (
        BLUE + "SIMULATOR" + RESET + GRAY + " │ " + RESET
        + WHITE + f"Market: {status}" + RESET + GRAY + " │ " + RESET
        + WHITE + clock + RESET + GRAY + f" │ tick #{tick}" + RESET
    )
    pad = max(1, width - visible_len(left) - visible_len(right))
    lines.append(left + " " * pad + right)
    lines.append(rule)

    # Ticker tape
    tape_cells = build_tape(symbols, quotes)
    lines.append(render_tape(tape_cells, tape_offset, width))
    lines.append(rule)

    # Quote table
    lines.extend(render_table(symbols, quotes, history, tick_dir, focus, width))
    lines.append(rule)

    # Big chart for the focused ticker
    used = len(lines) + 3  # title + footer + breathing room
    chart_h = max(6, min(14, rows - used - 1))
    try:
        info = sim.get_company_info(focus)
        title_txt = f"{focus} — {info.name} ({info.sector})"
    except Exception:
        title_txt = focus
    q = quotes[focus]
    lines.append(
        " " + BOLD + YELLOW + title_txt + RESET
        + trend_color(q.change) + f"   {q.price:,.2f} ({q.change_percent:+.2f}%)" + RESET
        + DIM + f"   rotates every {rotate_secs:.0f}s" + RESET
    )
    lines.extend(render_chart(history[focus], width - 2, chart_h))

    # Footer
    lines.append(
        DIM + " Ctrl+C to quit · simulated data (geometric Brownian motion) · "
        "provider: SIMULATOR via UnifiedMarketData" + RESET
    )

    body = "\n".join(clip(line, width) + CLEAR_EOL for line in lines)
    return HOME + body + "\n" + CLEAR_BELOW


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="FinAlly live market data terminal demo (simulated, offline)."
    )
    p.add_argument("symbols", nargs="*", default=None,
                   help=f"Ticker symbols to watch (default: {' '.join(DEFAULT_SYMBOLS)})")
    p.add_argument("--refresh", type=float, default=1.0,
                   help="Seconds between updates (default: 1.0, min: 0.3)")
    p.add_argument("--rotate", type=float, default=8.0,
                   help="Seconds before the big chart rotates to the next ticker (default: 8)")
    p.add_argument("--ticks", type=int, default=None,
                   help="Run a fixed number of frames then exit (default: run until Ctrl+C)")
    p.add_argument("--seed", type=int, default=42,
                   help="Simulator random seed (default: 42)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    refresh = max(0.3, args.refresh)
    rotate_secs = max(1.0, args.rotate)
    symbols = [s.upper() for s in (args.symbols or DEFAULT_SYMBOLS)]
    # de-duplicate, preserving order
    symbols = list(dict.fromkeys(symbols))

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sim = MarketDataSimulator(seed=args.seed)
    umd = UnifiedMarketData(providers=[sim])

    history: Dict[str, Deque[float]] = {s: deque(maxlen=400) for s in symbols}
    for s in symbols:
        history[s].extend(prefill_history(sim, umd, s, points=300))

    last_price: Dict[str, float] = {s: history[s][-1] for s in symbols}

    enable_ansi()
    sys.stdout.write(ALT_SCREEN_ON)
    sys.stdout.flush()

    tick = 0
    start = time.monotonic()
    try:
        while args.ticks is None or tick < args.ticks:
            quotes = umd.get_quotes(symbols, use_cache=False)
            tick_dir: Dict[str, float] = {}
            for s in symbols:
                price = quotes[s].price
                tick_dir[s] = price - last_price.get(s, price)
                last_price[s] = price
                history[s].append(price)

            elapsed = time.monotonic() - start
            focus = symbols[int(elapsed // rotate_secs) % len(symbols)]
            frame = render_frame(
                symbols, quotes, history, tick_dir, umd, sim,
                focus, tape_offset=tick * 3, tick=tick, rotate_secs=rotate_secs,
            )
            sys.stdout.write(frame)
            sys.stdout.flush()
            tick += 1
            if args.ticks is not None and tick >= args.ticks:
                break
            time.sleep(refresh)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(ALT_SCREEN_OFF)
        sys.stdout.flush()

    print(f"FinAlly market data demo finished — {tick} update(s) across "
          f"{len(symbols)} ticker(s): {', '.join(symbols)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
