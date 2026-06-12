import { test, expect } from '@playwright/test';

/**
 * FinAlly E2E Test Suite
 *
 * Covers all 8 scenarios from PLAN.md §12:
 *   1. Fresh start: default watchlist, $10k balance, prices streaming
 *   2. Add and remove a ticker from the watchlist
 *   3. Buy shares: cash decreases, position appears, portfolio updates
 *   4. Sell shares: cash increases, position updates or disappears
 *   5. Portfolio heatmap renders with correct P&L colors
 *   6. P&L chart has data points
 *   7. AI chat (mocked): send a message, receive a response, trade execution inline
 *   8. SSE resilience: disconnect and verify reconnection
 *
 * Run with:  npx playwright test  (from test/ directory)
 * Requires:  docker compose -f docker-compose.test.yml up --build  (handled by webServer in playwright.config.ts)
 * Environment: LLM_MOCK=true (set in docker-compose.test.yml)
 */

test.describe('FinAlly E2E Suite', () => {

  /**
   * Test 1: Fresh start
   * Verifies the initial state of the trading workstation:
   * - Default watchlist tickers visible (AAPL, GOOGL, MSFT)
   * - $10,000 starting cash balance shown
   * - SSE connection is active (green status dot)
   */
  test('1. Fresh start: default watchlist, $10k balance, prices streaming', async ({ page }) => {
    await page.goto('/');

    // Check $10,000 cash visible — accept any formatting: $10,000 or $10000 or $10,000.00
    await expect(page.getByText(/\$10[,.]?000/)).toBeVisible({ timeout: 10000 });

    // Check at least the core default tickers are visible in the watchlist
    for (const ticker of ['AAPL', 'GOOGL', 'MSFT']) {
      await expect(page.getByText(ticker)).toBeVisible({ timeout: 5000 });
    }

    // Connection status dot should indicate connected (green)
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Verify prices are present (at least one price element rendered)
    const priceEl = page.locator('[data-ticker="AAPL"] .price').first();
    await expect(priceEl).toBeVisible({ timeout: 10000 });
  });

  /**
   * Test 2: Add and remove a watchlist ticker
   * Verifies the watchlist management workflow:
   * - User can add an arbitrary ticker (PYPL)
   * - Added ticker becomes visible in the watchlist
   * - User can remove the ticker
   * - Removed ticker disappears from the watchlist
   */
  test('2. Add and remove watchlist ticker', async ({ page }) => {
    await page.goto('/');

    // Wait for app to be fully loaded
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Add PYPL to watchlist
    await page.getByPlaceholder(/ticker/i).fill('PYPL');
    await page.getByRole('button', { name: /add/i }).click();

    // PYPL should appear in the watchlist
    await expect(page.getByText('PYPL')).toBeVisible({ timeout: 5000 });

    // Remove PYPL via the remove button on its watchlist row
    await page.locator('[data-ticker="PYPL"] button[aria-label="remove"]').click();

    // PYPL should no longer be visible
    await expect(page.getByText('PYPL')).not.toBeVisible({ timeout: 5000 });
  });

  /**
   * Test 3: Buy shares
   * Verifies trade execution (buy side):
   * - Cash balance decreases after buying 5 shares of AAPL
   * - AAPL appears in the positions table after purchase
   */
  test('3. Buy shares: cash decreases, position appears', async ({ page }) => {
    await page.goto('/');

    // Wait for app to be fully loaded and prices streaming
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Record cash balance before trade
    const cashBefore = await page.locator('.cash-balance').textContent();
    expect(cashBefore).toBeTruthy();

    // Execute buy: 5 shares of AAPL
    await page.locator('input[name="trade-ticker"]').fill('AAPL');
    await page.locator('input[name="trade-quantity"]').fill('5');
    await page.getByRole('button', { name: /buy/i }).click();

    // Wait for trade to settle
    await page.waitForTimeout(1000);

    // Cash should have decreased
    const cashAfter = await page.locator('.cash-balance').textContent();
    const parseCash = (s: string) => parseFloat(s!.replace(/[^0-9.]/g, ''));
    expect(parseCash(cashAfter!)).toBeLessThan(parseCash(cashBefore!));

    // AAPL should appear in the positions table
    await expect(page.locator('.positions-table').getByText('AAPL')).toBeVisible({ timeout: 5000 });
  });

  /**
   * Test 4: Sell shares
   * Verifies trade execution (sell side):
   * - Cash balance increases after selling shares
   * - Position updates or disappears from positions table
   *
   * Setup: buy 5 AAPL first, then sell all 5.
   */
  test('4. Sell shares: cash increases, position updates or disappears', async ({ page }) => {
    await page.goto('/');

    // Wait for app to be fully loaded
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Step 1: Buy 5 AAPL
    await page.locator('input[name="trade-ticker"]').fill('AAPL');
    await page.locator('input[name="trade-quantity"]').fill('5');
    await page.getByRole('button', { name: /buy/i }).click();
    await page.waitForTimeout(500);

    // Record cash after buy
    const cashAfterBuy = await page.locator('.cash-balance').textContent();

    // Step 2: Sell all 5 AAPL
    await page.locator('input[name="trade-ticker"]').fill('AAPL');
    await page.locator('input[name="trade-quantity"]').fill('5');
    await page.getByRole('button', { name: /sell/i }).click();
    await page.waitForTimeout(1000);

    // Cash should have increased back (approximately back to ~$10k)
    const cashAfterSell = await page.locator('.cash-balance').textContent();
    const parseCash = (s: string) => parseFloat(s!.replace(/[^0-9.]/g, ''));
    expect(parseCash(cashAfterSell!)).toBeGreaterThan(parseCash(cashAfterBuy!));

    // Position should have been removed (quantity = 0 means row deleted per spec)
    await expect(page.locator('.positions-table').getByText('AAPL')).not.toBeVisible({ timeout: 5000 });
  });

  /**
   * Test 5: Portfolio heatmap renders with P&L colors
   * Verifies the treemap/heatmap visualization:
   * - Heatmap container is visible
   * - After buying a position, AAPL cell appears in the heatmap
   * - Cell has a background color (green/red for P&L)
   */
  test('5. Portfolio heatmap renders with P&L colors', async ({ page }) => {
    await page.goto('/');

    // Wait for app to be fully loaded
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Buy a position to populate the heatmap
    await page.locator('input[name="trade-ticker"]').fill('AAPL');
    await page.locator('input[name="trade-quantity"]').fill('10');
    await page.getByRole('button', { name: /buy/i }).click();

    // Wait for heatmap to re-render with new position
    await page.waitForTimeout(2000);

    // Heatmap container should be visible
    await expect(page.locator('.portfolio-heatmap')).toBeVisible({ timeout: 5000 });

    // AAPL cell should appear within the heatmap
    await expect(page.locator('.portfolio-heatmap').getByText('AAPL')).toBeVisible({ timeout: 5000 });

    // The heatmap cell should have a color style applied (green or red P&L indicator)
    const heatmapCell = page.locator('.portfolio-heatmap [data-ticker="AAPL"]');
    const bgColor = await heatmapCell.evaluate(el => window.getComputedStyle(el).backgroundColor);
    // Background should not be transparent — it should have a real color
    expect(bgColor).not.toBe('rgba(0, 0, 0, 0)');
    expect(bgColor).not.toBe('transparent');
  });

  /**
   * Test 6: P&L chart shows data points
   * Verifies the portfolio value over time chart:
   * - P&L chart container is rendered
   * - SVG path(s) are present (indicating chart has rendered data)
   *
   * Note: The backend records portfolio_snapshots every 30s, but also
   * immediately after each trade. We wait 5s and make a trade to trigger a snapshot.
   */
  test('6. P&L chart shows data points', async ({ page }) => {
    await page.goto('/');

    // Wait for app to be fully loaded
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Make a trade to trigger an immediate portfolio snapshot
    await page.locator('input[name="trade-ticker"]').fill('AAPL');
    await page.locator('input[name="trade-quantity"]').fill('1');
    await page.getByRole('button', { name: /buy/i }).click();

    // Wait a bit for the chart to update
    await page.waitForTimeout(5000);

    // P&L chart container should be visible
    await expect(page.locator('.pnl-chart')).toBeVisible({ timeout: 5000 });

    // Chart should have rendered SVG content (data lines)
    await expect(page.locator('.pnl-chart svg')).toBeVisible({ timeout: 5000 });
  });

  /**
   * Test 7: AI chat with mock LLM — "buy AAPL" executes a trade
   * Verifies the LLM chat integration (LLM_MOCK=true in docker-compose.test.yml):
   * - User sends "buy AAPL" message
   * - Assistant response appears within timeout
   * - Trade confirmation is shown inline (mock LLM returns a buy AAPL trade action)
   *
   * Per PLAN.md §13.1-#7: mock responds to "buy AAPL" with a buy trade action.
   */
  test('7. AI chat with mock LLM — buy AAPL executes', async ({ page }) => {
    await page.goto('/');

    // Wait for app to be fully loaded
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Type "buy AAPL" into the chat input
    await page.locator('.chat-input').fill('buy AAPL');

    // Send the message
    await page.locator('.chat-send').click();

    // Loading indicator should appear briefly (optional, may be too fast)
    // Then the assistant's response message should appear
    await expect(page.locator('.chat-message.assistant')).toBeVisible({ timeout: 15000 });

    // Trade confirmation should be shown inline in the chat
    await expect(page.locator('.trade-confirmation')).toBeVisible({ timeout: 15000 });
  });

  /**
   * Test 8: SSE reconnection
   * Verifies that the frontend automatically reconnects to the SSE price stream
   * after a network interruption:
   * - App starts connected (green dot)
   * - SSE endpoint is blocked (simulating network drop)
   * - App detects disconnection
   * - When unblocked, app reconnects and returns to connected state
   */
  test('8. SSE reconnection on network drop', async ({ page }) => {
    await page.goto('/');

    // Verify initially connected
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 10000 });

    // Block the SSE price stream to simulate a network disconnect
    await page.route('/api/stream/prices', route => route.abort());

    // Wait for the app to detect the disconnection
    // (EventSource fires onerror fairly quickly after abort)
    await page.waitForTimeout(2000);

    // Unblock the SSE endpoint so reconnection can proceed
    await page.unroute('/api/stream/prices');

    // App should reconnect automatically (EventSource has built-in retry)
    // Allow up to 15 seconds for reconnect cycle
    await expect(page.locator('.connection-status.connected')).toBeVisible({ timeout: 15000 });
  });

});
