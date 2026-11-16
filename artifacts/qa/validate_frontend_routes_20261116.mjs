import { createRequire } from 'node:module'
import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

const root = process.cwd()
const require = createRequire(path.join(root, 'frontend/package.json'))
const { chromium, expect } = require('@playwright/test')
const output = path.join(root, 'artifacts/qa/validation-20261116')
const source = await readFile(path.join(root, 'frontend/src/App.tsx'), 'utf8')
const routes = [...source.matchAll(/<Route path="([^"]+)" element=\{<(?:Strict)?ProtectedRoute/g)]
  .map(match => match[1].replace(/:[\w]+/g, '999999'))
const results = []
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
try {
  const context = await browser.newContext({ reducedMotion: 'reduce' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  for (const route of routes) {
    try {
      await page.goto(`http://127.0.0.1:34119${route}`)
      await expect(page).toHaveURL(/\/(?:employee-)?login(?:\?|$)/)
      await expect(page.locator('input[type="password"]')).toBeVisible()
      results.push({ route, passed: true })
    } catch (error) {
      results.push({ route, passed: false, error: error.message })
    }
  }
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('http://127.0.0.1:34119/')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/Organization\s*Improvement Process/)
    await expect(page.locator('.rosette-hero__division')).toHaveCount(6)
    await page.screenshot({ path: path.join(output, `welcome-${width}.png`), fullPage: true })
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    results.push({ route: '/', viewport_width: width, passed: !overflow, horizontal_overflow: overflow })
    await page.getByRole('link', { name: 'Login', exact: true }).click()
    await expect(page.locator('input[type="password"]')).toBeVisible()
  }
  const report = { protected_routes_checked: routes.length, results, page_errors: errors,
    passed: results.every(row => row.passed) && errors.length === 0 }
  await writeFile(path.join(output, 'frontend-routes.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ protected_routes_checked: routes.length, passed: report.passed,
    failures: results.filter(row => !row.passed), page_errors: errors }, null, 2))
  if (!report.passed) process.exitCode = 1
} finally {
  await browser.close()
}
