import { test, expect, Page, Locator } from '@playwright/test';

/**
 * FinAlly E2E Test Suite — all 8 scenarios from PLAN.md §12.
 *
 * Selectors are matched to the ACTUAL frontend DOM (frontend/components/):
 *  - Connection status: header text "LIVE" / "RECONNECTING" / "DISCONNECTED"
 *  - Cash balance: span following the "CASH" label in the header
 *  - Panels are identified by their title spans: "WATCHLIST", "POSITIONS",
 *    "PORTFOLIO HEATMAP", "PORTFOLIO P&L"
 *  - Trade bar: placeholders "TICKER" / "QTY", buttons "BUY" / "SELL"
 *  - Watchlist add: placeholder "ADD TICKER", button "+"
 *  - Chat: textarea placeholder "Ask FinAlly...", button "SEND"
 *  - Mock LLM (LLM_MOCK=true): "buy AAPL" -> buys 5 AAPL, replies
 *    "Buying 5 shares of AAPL for you."
 *
 * State note: all tests share one backend DB (workers=1, sequential).
 * run-server.cjs wipes test-db before each suite run, so test 1 always
 * sees the fresh-seeded $10,000 balance.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Panel root: the div whose direct-child header div contains the title span. */
function panel(page: Page, title: string): Locator {
  return page.locator(`div:has(> div > span:text-is("${title}"))`);
}

/** Cash balance value span in the header (sibling of the "CASH" label). */
function cashValue(page: Page): Locator {
  return page.locator('xpath=//span[text()="CASH"]/following-sibling::span');
}

function parseMoney(text: string | null): number {
  return parseFloat((text ?? '').replace(/[^0-9.\-]/g, ''));
}

/** Wait for the SSE connection indicator to show connected. */
async function waitForConnected(page: Page): Promise<void> {
  await expect(page.getByText('LIVE', { exact: true })).toBeVisible({ timeout: 15000 });
}

/** Execute a manual trade via the trade bar and wait for the success toast. */
async function trade(page: Page, side: 'BUY' | 'SELL', ticker: string, qty: number): Promise<void> {
  await page.getByPlaceholder('TICKER', { exact: true }).fill(ticker);
  await page.getByPlaceholder('QTY', { exact: true }).fill(String(qty));
  await page.getByRole('button', { name: side, exact: true }).click();
  // TradeBar shows "✓ BUY 5 AAPL @ $190.12" on success
  await expect(
    page.getByText(new RegExp(`${side} ${qty} ${ticker} @ \\$`))
  ).toBeVisible({ timeout: 10000 });
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

test.describe('FinAlly E2E Suite', () => {

  /**
   * 1. Fresh start: default watchlist, $10k balance, prices streaming.
   */
  test('1. Fresh start: default watchlist, $10k balance, prices streaming', async ({ page }) => {
    await page.goto('/');

    // Connection dot/label green ("LIVE")
    await waitForConnected(page);

    // $10,000.00 starting cash in the header
    await expect(cashValue(page)).toHaveText(/\$10,000\.00/, { timeout: 10000 });

    // Default tickers visible in the watchlist panel
    const watchlist = panel(page, 'WATCHLIST');
    for (const ticker of ['AAPL', 'GOOGL', 'MSFT']) {
      await expect(watchlist.getByText(ticker, { exact: true })).toBeVisible({ timeout: 5000 });
    }

    // Prices are streaming: AAPL price fills in, then changes over time
    const aaplRow = watchlist.locator('.grid').filter({ hasText: 'AAPL' });
    const priceSpan = aaplRow.locator('span.font-mono').first();
    await expect(priceSpan).not.toHaveText('--', { timeout: 15000 });
    const initialPrice = await priceSpan.textContent();
    await expect
      .poll(async () => priceSpan.textContent(), { timeout: 15000 })
      .not.toBe(initialPrice);
  });

  /**
   * 2. Add and remove a ticker from the watchlist.
   */
  test('2. Add and remove watchlist ticker', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    const watchlist = panel(page, 'WATCHLIST');

    // Add PYPL
    await page.getByPlaceholder('ADD TICKER').fill('PYPL');
    await page.getByRole('button', { name: '+', exact: true }).click();
    await expect(watchlist.getByText('PYPL', { exact: true })).toBeVisible({ timeout: 5000 });

    // Remove PYPL via the remove control on its watchlist row
    const pyplRow = watchlist.locator('.grid').filter({ hasText: 'PYPL' });
    await pyplRow.hover(); // remove buttons are often hover-revealed
    await pyplRow.getByRole('button', { name: /remove|×|✕|x/i }).click({ timeout: 5000 });
    await expect(watchlist.getByText('PYPL', { exact: true })).not.toBeVisible({ timeout: 5000 });
  });

  /**
   * 3. Buy shares: cash decreases, position appears.
   */
  test('3. Buy shares: cash decreases, position appears', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    // Record cash before the trade
    await expect(cashValue(page)).toHaveText(/\$/, { timeout: 10000 });
    const cashBefore = parseMoney(await cashValue(page).textContent());

    // Buy 5 AAPL
    await trade(page, 'BUY', 'AAPL', 5);

    // Cash decreases (header refreshes right after the trade)
    await expect
      .poll(async () => parseMoney(await cashValue(page).textContent()), { timeout: 10000 })
      .toBeLessThan(cashBefore);

    // AAPL appears in the positions table
    await expect(
      panel(page, 'POSITIONS').getByText('AAPL', { exact: true })
    ).toBeVisible({ timeout: 10000 });
  });

  /**
   * 4. Sell shares: cash increases, position updates.
   */
  test('4. Sell shares: cash increases', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    await expect(cashValue(page)).toHaveText(/\$/, { timeout: 10000 });
    const cashStart = parseMoney(await cashValue(page).textContent());

    // Buy 5 AAPL, wait for cash to settle below the starting value
    await trade(page, 'BUY', 'AAPL', 5);
    await expect
      .poll(async () => parseMoney(await cashValue(page).textContent()), { timeout: 10000 })
      .toBeLessThan(cashStart);
    const cashAfterBuy = parseMoney(await cashValue(page).textContent());

    // Sell the 5 AAPL back
    await trade(page, 'SELL', 'AAPL', 5);

    // Cash increases again (sell proceeds credited)
    await expect
      .poll(async () => parseMoney(await cashValue(page).textContent()), { timeout: 10000 })
      .toBeGreaterThan(cashAfterBuy);
  });

  /**
   * 5. Portfolio heatmap renders with P&L colors.
   */
  test('5. Portfolio heatmap renders with P&L colors', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    // Ensure there is a position to render
    await trade(page, 'BUY', 'AAPL', 10);

    const heatmap = panel(page, 'PORTFOLIO HEATMAP');
    await expect(heatmap).toBeVisible({ timeout: 5000 });

    // AAPL cell label rendered inside the treemap SVG
    await expect(heatmap.getByText('AAPL', { exact: true })).toBeVisible({ timeout: 10000 });

    // The cell rect must carry a computed P&L color (rgb(...) from lerpColor)
    const fill = await heatmap.locator('svg rect').first().getAttribute('fill');
    expect(fill).toMatch(/^rgb\(/);
  });

  /**
   * 6. P&L chart shows data points.
   * Snapshots are recorded every 30s and immediately after each trade —
   * earlier tests in this suite have already generated several.
   */
  test('6. P&L chart shows data points', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    // Trigger one more snapshot so the chart has >= 2 points even when
    // this test is run in isolation against a fresh DB
    await trade(page, 'BUY', 'AAPL', 1);

    const plChart = panel(page, 'PORTFOLIO P&L');
    await expect(plChart).toBeVisible({ timeout: 5000 });

    // Recharts renders the series as an SVG path with .recharts-line-curve
    await expect(plChart.locator('path.recharts-line-curve')).toBeVisible({ timeout: 20000 });
  });

  /**
   * 7. AI chat with mock LLM — "buy AAPL" executes a trade inline.
   * LLM_MOCK=true: "buy AAPL" -> trade {AAPL, buy, 5} + fixed message.
   */
  test('7. AI chat with mock LLM — buy AAPL executes', async ({ page }) => {
    await page.goto('/');
    await waitForConnected(page);

    // Send "buy AAPL" to the assistant
    await page.getByPlaceholder(/Ask FinAlly/).fill('buy AAPL');
    await page.getByRole('button', { name: 'SEND', exact: true }).click();

    // Mock assistant response appears
    await expect(
      page.getByText('Buying 5 shares of AAPL for you.')
    ).toBeVisible({ timeout: 15000 });

    // Executed-trade confirmation chip appears inline ("BUY 5 AAPL @ $...")
    await expect(page.getByText(/BUY 5 AAPL @ \$/)).toBeVisible({ timeout: 15000 });
  });

  /**
   * 8. SSE resilience: disconnect and verify automatic reconnection.
   * context.setOffline() severs the open EventSource connection (a
   * page.route() abort would only affect NEW requests, not the live stream).
   */
  test('8. SSE reconnection after network drop', async ({ page, context }) => {
    await page.goto('/');
    await waitForConnected(page);

    // Drop the network: the EventSource errors out and the UI leaves "LIVE"
    await context.setOffline(true);
    await expect(page.getByText(/DISCONNECTED|RECONNECTING/)).toBeVisible({ timeout: 10000 });

    // Restore the network: the hook retries every 3s and should reconnect
    await context.setOffline(false);
    await waitForConnected(page);
  });
});
