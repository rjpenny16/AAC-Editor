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
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python -m tdsnap.web --no-browser --port 8765',
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
