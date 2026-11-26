import { spawn } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const envText = readFileSync(new URL('../../.env', import.meta.url), 'utf8')
const env = Object.fromEntries(envText.split(/\r?\n/).filter(line => line && !line.startsWith('#') && line.includes('=')).map(line => {
  const index = line.indexOf('=')
  return [line.slice(0, index), line.slice(index + 1)]
}))

const authResponse = await fetch('http://127.0.0.1:3100/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: env.SEED_ADMIN_EMAIL, password: env.SEED_ADMIN_PASSWORD }),
})
const auth = await authResponse.json()
if (!authResponse.ok || !auth.access_token || !auth.user) {
  throw new Error(`Visual QA login unavailable (${authResponse.status})`)
}

const outputDir = mkdtempSync(join(tmpdir(), 'naksha-ui-qa-'))
const profileDir = mkdtempSync(join(tmpdir(), 'naksha-chrome-'))
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', [
  '--headless=new',
  '--disable-gpu',
  '--no-first-run',
  '--no-default-browser-check',
  '--remote-debugging-port=9237',
  `--user-data-dir=${profileDir}`,
  'about:blank',
], { stdio: 'ignore', windowsHide: true })

async function waitForDebugger() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const pages = await fetch('http://127.0.0.1:9237/json/list').then(response => response.json())
      const page = pages.find(item => item.type === 'page')
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl
    } catch { /* Chrome is still starting. */ }
    await delay(250)
  }
  throw new Error('Chrome DevTools endpoint did not start')
}

const socket = new WebSocket(await waitForDebugger())
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

let commandId = 0
const pending = new Map()
socket.addEventListener('message', event => {
  const message = JSON.parse(String(event.data))
  if (!message.id || !pending.has(message.id)) return
  const { resolve, reject } = pending.get(message.id)
  pending.delete(message.id)
  if (message.error) reject(new Error(message.error.message))
  else resolve(message.result)
})

function command(method, params = {}) {
  commandId += 1
  const id = commandId
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Browser evaluation failed')
  return result.result.value
}

async function navigate(path) {
  await command('Page.navigate', { url: `http://127.0.0.1:3100${path}` })
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await evaluate('document.readyState === "complete"')) break
    await delay(150)
  }
  await delay(2600)
}

async function screenshot(name) {
  const result = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  const path = join(outputDir, `${name}.png`)
  writeFileSync(path, Buffer.from(result.data, 'base64'))
  return path
}

function metricsExpression() {
  return `(() => {
    const shell = document.querySelector('.app-shell');
    const hero = document.querySelector('.nk-hero');
    const title = hero?.querySelector('h1');
    const kicker = hero?.querySelector('.nk-hero-fold-top');
    const description = hero?.querySelector('.nk-hero-fold-bottom');
    const cards = [...document.querySelectorAll('.stat-card, .sr-kpi-grid article, .finance-kpi-card[data-kpi]')];
    const firstCard = cards[0];
    const firstIcon = firstCard?.querySelector('.stat-icon, svg');
    const heroStyle = hero ? getComputedStyle(hero) : null;
    const cardStyle = firstCard ? getComputedStyle(firstCard) : null;
    const iconStyle = firstIcon ? getComputedStyle(firstIcon) : null;
    return {
      location: location.pathname,
      department: shell?.dataset.dept ?? null,
      hero: Boolean(hero),
      collapsed: hero?.classList.contains('is-collapsed') ?? false,
      heroPosition: heroStyle?.position ?? null,
      heroTop: heroStyle?.top ?? null,
      heroHeight: hero ? Math.round(hero.getBoundingClientRect().height) : null,
      heroViewportTop: hero ? Math.round(hero.getBoundingClientRect().top) : null,
      title: title?.textContent?.trim() ?? null,
      kickerOpacity: kicker ? getComputedStyle(kicker).opacity : null,
      descriptionOpacity: description ? getComputedStyle(description).opacity : null,
      cardCount: cards.length,
      cardHeight: firstCard ? Math.round(firstCard.getBoundingClientRect().height) : null,
      cardRadius: cardStyle?.borderRadius ?? null,
      iconSize: firstIcon ? [Math.round(firstIcon.getBoundingClientRect().width), Math.round(firstIcon.getBoundingClientRect().height)] : null,
    };
  })()`
}

try {
  await command('Page.enable')
  await command('Runtime.enable')
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await navigate('/login')
  await evaluate(`localStorage.setItem('asset_token', ${JSON.stringify(auth.access_token)}); localStorage.setItem('asset_user', ${JSON.stringify(JSON.stringify(auth.user))}); localStorage.setItem('asset_branch_required', 'false');`)

  const routes = [
    ['finance-command', '/finance/command-center'],
    ['sales', '/finance/sales'],
    ['revenue', '/finance/revenue'],
    ['admin', '/admin'],
    ['bd', '/bd'],
    ['management', '/management'],
    ['it', '/it'],
    ['drone', '/drone'],
    ['ortho', '/ortho'],
  ]
  const report = []

  for (const [name, route] of routes) {
    await navigate(route)
    await evaluate('window.scrollTo(0, 0)')
    await delay(650)
    const expanded = await evaluate(metricsExpression())
    const expandedImage = await screenshot(`${name}-expanded`)
    await evaluate('window.scrollTo(0, 520)')
    await delay(750)
    const collapsed = await evaluate(metricsExpression())
    const collapsedImage = await screenshot(`${name}-collapsed`)
    report.push({ name, expanded, collapsed, images: [expandedImage, collapsedImage] })
  }

  console.log(JSON.stringify({ outputDir, report }, null, 2))
} finally {
  socket.close()
  chrome.kill()
}
