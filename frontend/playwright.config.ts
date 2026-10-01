import { defineConfig } from '@playwright/test'

// Runs against the real stack: `make infra` first, then this starts the API and web app if they aren't up.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  workers: 1,
  use: { baseURL: 'http://localhost:5180', trace: 'retain-on-failure' },
  webServer: [
    { command: 'cd ../backend && uv run uvicorn app.main:app --port 8010', url: 'http://localhost:8010/api/health', reuseExistingServer: true },
    { command: 'pnpm dev', url: 'http://localhost:5180', reuseExistingServer: true },
  ],
})
