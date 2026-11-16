import path from 'node:path'
import base from './playwright.config'

const cwd = process.cwd()
const servers = base.webServer as { command: string; [key: string]: unknown }[]
export default {
  ...base,
  testDir: './e2e',
  use: { ...base.use, launchOptions: { executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' } },
  webServer: [
    { ...servers[0], cwd, command: `"${path.resolve('../backend/.venv/Scripts/python.exe')}" ../artifacts/qa/module_audit_browser_server.py` },
    { ...servers[1], cwd },
  ],
}
