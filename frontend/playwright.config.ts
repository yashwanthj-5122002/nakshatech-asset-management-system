import { defineConfig } from '@playwright/test'
import path from 'node:path'

const python = process.env.ERP_TEST_PYTHON || (process.platform === 'win32'
  ? path.resolve('../backend/.venv/Scripts/python.exe') : 'python')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: {
    baseURL: 'http://127.0.0.1:34110',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {},
  },
  webServer: [
    {
      command: `"${python}" ../backend/tests/browser_server.py`,
      url: 'http://127.0.0.1:38111/api/health',
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 34110 --strictPort',
      url: 'http://127.0.0.1:34110/e2e/workflow.html',
      env: { VITE_API_URL: 'http://127.0.0.1:38111/api' },
      reuseExistingServer: false,
    },
  ],
})
