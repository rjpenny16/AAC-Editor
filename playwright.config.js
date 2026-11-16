const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.js',
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://127.0.0.1:8765',
    browserName: 'chromium',
    // PW_CHANNEL=msedge runs the suite in installed Edge (the Windows CI job),
    // which is the engine the desktop window uses.
    ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}),
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python -m tdsnap.web --no-browser --port 8765',
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: false,
    // One access-log line per request buried failures in CI logs (doc 05:
    // a failed run must keep its evidence). Errors still print.
    env: { AAC_QUIET_HTTP_LOG: '1' },
    timeout: 30_000,
  },
});
