import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: 2,
  workers: 1, // tests share one backend DB — must run sequentially
  globalTeardown: './global-teardown.cjs',
  use: {
    baseURL: 'http://localhost:8001',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: {
    // run-server.cjs tears down stale containers, resets test-db, then
    // runs `docker compose -f docker-compose.test.yml up --build`
    command: 'node run-server.cjs',
    url: 'http://localhost:8001/api/health',
    timeout: 240000, // generous: first run includes a full Docker image build
    reuseExistingServer: false,
  },
});
