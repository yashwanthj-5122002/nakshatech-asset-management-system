import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

// A real Chromium check using its native DevTools protocol; no extra package required.
// Run from frontend: node scripts/verify-welcome-browser.mjs [http://localhost:3100] [webgl]
const url = process.argv[2] ?? 'http://localhost:3100'
const graphicsEnabled = process.argv[3] === 'webgl'
const captureScreenshots = !process.argv.includes('--no-screenshots')
const chromePath = process.env.CHROME_PATH ?? path.join(os.homedir(), 'AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe')
const artifacts = path.resolve(`artifacts/welcome-rosette-loop${graphicsEnabled ? '-webgl' : ''}`)
await fs.mkdir(artifacts, { recursive: true })
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'naksha-welcome-check-'))
const graphicsFlags = graphicsEnabled ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] : ['--disable-gpu']
const browser = spawn(chromePath, ['--headless', ...graphicsFlags, '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
let socket
let id = 0
let sessionId
const requests = new Map()
const errors = []
const results = []
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
try {
  const endpoint = await new Promise((resolve, reject) => {
    let output = ''
    const timeout = setTimeout(() => reject(new Error('Chromium did not start')), 15000)
    browser.once('error', reject)
    browser.stderr.on('data', data => {
      output += data
      const match = output.match(/DevTools listening on (ws:\/\/\S+)/)
      if (match) { clearTimeout(timeout); resolve(match[1]) }
    })
  })
  socket = new WebSocket(endpoint)
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }) })
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data)
    if (message.id) {
      const request = requests.get(message.id)
      if (request) {
        requests.delete(message.id)
        clearTimeout(request.timeout)
        if (message.error) request.reject(new Error(JSON.stringify(message.error)))
        else request.resolve(message.result)
      }
    }
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text + ': ' + (message.params.exceptionDetails.exception?.description ?? ''))
    if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') errors.push(message.params.entry.text)
  })
  const cdp = (method, params = {}, targetSession = sessionId) => new Promise((resolve, reject) => {
    const requestId = ++id
    const timeout = setTimeout(() => { requests.delete(requestId); reject(new Error(`Timed out: ${method} ${params.expression?.slice(0, 100) ?? ''}`)) }, method === 'Page.captureScreenshot' ? 30000 : 15000)
    requests.set(requestId, { resolve, reject, timeout })
    socket.send(JSON.stringify({ id: requestId, method, params, ...(targetSession ? { sessionId: targetSession } : {}) }))
  })
  const target = await cdp('Target.createTarget', { url: 'about:blank' })
  sessionId = (await cdp('Target.attachToTarget', { targetId: target.targetId, flatten: true })).sessionId
  await cdp('Page.enable')
  await cdp('Runtime.enable')
  await cdp('Log.enable')
  const evaluate = async expression => {
    const result = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
    return result.result.value
  }
  const waitFor = async expression => {
    for (let attempt = 0; attempt < 100; attempt++) { if (await evaluate(`Boolean(${expression})`)) return; await delay(150) }
    const diagnostic = await evaluate(`({ url: location.href, title: document.title, text: document.body.innerText.slice(0, 2000), errors: ${JSON.stringify(errors)} })`)
    console.error(JSON.stringify(diagnostic, null, 2))
    const screenshot = await cdp('Page.captureScreenshot', { format: 'png' })
    await fs.writeFile(path.join(artifacts, 'failed-condition.png'), Buffer.from(screenshot.data, 'base64'))
    throw new Error(`Page condition failed: ${expression}`)
  }
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false })
  await cdp('Page.navigate', { url })
  await waitFor(`document.querySelectorAll('.rosette-hero__division').length === 6`)
  if (graphicsEnabled) await waitFor(`document.querySelector('.rosette-hero--webgl')`)
  assert.equal(await evaluate(`document.querySelector('#space-welcome-title').innerText.replace(/\\s+/g, ' ').trim()`), 'Organization Improvement Process', 'Requested welcome heading missing')
  assert.equal(await evaluate(`document.querySelector('.space-welcome__description').textContent.replace(/\\s+/g, ' ').trim()`), 'Manage IT assets, drone operations, and workflows in one intelligent platform.', 'Original description changed')
  assert.equal(await evaluate(`document.querySelector('.space-welcome__login').textContent.trim()`), 'Login', 'Original Login label changed')
  await waitFor(`Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)`)

  const motionSamples = []
  if (graphicsEnabled) {
    await evaluate(`document.querySelector('[aria-label="Reset 3D view"]').click()`)
    await waitFor(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.extension) > .99`)
    const motionSample = () => evaluate(`(() => { const c = document.querySelector('.rosette-hero__webgl canvas'); return { extension: Number(c.dataset.extension), spin: Number(c.dataset.spin), labels: [...document.querySelectorAll('.rosette-hero__division')].map(button => ({ key: button.getAttribute('aria-label'), x: button.style.left, y: button.style.top, visible: getComputedStyle(button).visibility === 'visible' })) } })()`)
    motionSamples.push(await motionSample())
    if (process.argv.includes('--motion-preview')) {
      await evaluate(`document.querySelector('[aria-label="Pause visual animation"]').click()`)
      const expanded = await cdp('Page.captureScreenshot', { format: 'png', fromSurface: true, clip: { x: 0, y: 0, width: 1920, height: 1080, scale: .75 } })
      await fs.writeFile(path.join(artifacts, 'motion-expanded.png'), Buffer.from(expanded.data, 'base64'))
      await evaluate(`document.querySelector('[aria-label="Resume visual animation"]').click()`)
    }
    await waitFor(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.extension) < .01`)
    if (process.argv.includes('--motion-preview')) {
      await evaluate(`document.querySelector('[aria-label="Pause visual animation"]').click()`)
      const collapsed = await cdp('Page.captureScreenshot', { format: 'png', fromSurface: true, clip: { x: 0, y: 0, width: 1920, height: 1080, scale: .75 } })
      await fs.writeFile(path.join(artifacts, 'motion-collapsed.png'), Buffer.from(collapsed.data, 'base64'))
      await evaluate(`document.querySelector('[aria-label="Resume visual animation"]').click()`)
    }
    motionSamples.push(await motionSample())
    assert.ok(motionSamples[1].labels.every(label => !label.visible), 'Collapsed cubes must not pile division labels over the center')
    await waitFor(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.extension) > .99`)
    motionSamples.push(await motionSample())
    assert.ok(motionSamples[2].spin > motionSamples[0].spin + 1, 'Central cube and arms did not rotate through the loop')
    assert.ok(motionSamples[2].labels.some((label, index) => label.x !== motionSamples[0].labels[index].x || label.y !== motionSamples[0].labels[index].y), 'Labels did not follow rotating sub-cubes')
    await evaluate(`document.querySelector('[aria-label="Pause visual animation"]').click()`)
    const stopped = await motionSample()
    await delay(200)
    const stillStopped = await motionSample()
    assert.equal(stillStopped.extension, stopped.extension, 'Pause did not freeze expansion')
    assert.equal(stillStopped.spin, stopped.spin, 'Pause did not freeze rotation')
    await evaluate(`document.querySelector('[aria-label="Reset 3D view"]').click()`)
    await waitFor(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.extension) > .99`)
  }

  for (const [width, height] of [[1920, 1080], [1366, 768], [1024, 768], [768, 1024], [390, 844], [320, 740]]) {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    await evaluate('window.scrollTo(0, 0)')
    await delay(160)
    const layout = await evaluate(`(() => {
      const rect = element => { const r = element.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom } }
      const buttons = [...document.querySelectorAll('.rosette-hero__division')]
      const scene = rect(document.querySelector('.rosette-hero__scene'))
      const copy = rect(document.querySelector('.space-welcome__copy'))
      const visual = rect(document.querySelector('.space-welcome__visual'))
      return {
        overflow: document.documentElement.scrollWidth > innerWidth,
        scene, copy, visual,
        cubes: document.querySelectorAll('.rosette-cube').length,
        faces: document.querySelectorAll('.rosette-cube__face').length,
        divisions: buttons.map(button => ({ name: button.getAttribute('aria-label'), ...rect(button) })),
        login: rect(document.querySelector('.space-welcome__login')),
        preserve3d: [...document.querySelectorAll('.rosette-cube')].every(cube => getComputedStyle(cube).transformStyle === 'preserve-3d'),
        contentHeight: document.documentElement.scrollHeight
      }
    })()`)
    await fs.writeFile(path.join(artifacts, `layout-${width}.json`), JSON.stringify(layout, null, 2))
    assert.equal(layout.overflow, false, `${width}: horizontal overflow`)
    assert.equal(layout.cubes, 7, `${width}: hub and six cubes required`)
    assert.equal(layout.faces, 42, `${width}: every cube needs six faces`)
    assert.equal(layout.preserve3d, true, `${width}: 3D transforms flattened`)
    assert.ok(layout.login.x >= 0 && layout.login.right <= width, `${width}: login clipped`)
    for (const division of layout.divisions) {
      assert.ok(division.x >= layout.scene.x - 1 && division.right <= layout.scene.right + 1, `${width}: division clipped horizontally: ${division.name}`)
      assert.ok(division.y >= layout.scene.y - 1 && division.bottom <= layout.scene.bottom + 1, `${width}: division clipped vertically: ${division.name}`)
      assert.ok(division.width >= 44 && division.height >= 44, `${width}: division touch target too small`)
    }
    for (let i = 0; i < layout.divisions.length; i++) {
      for (const other of layout.divisions.slice(i + 1)) {
        const first = layout.divisions[i]
        assert.ok(first.right <= other.x || other.right <= first.x || first.bottom <= other.y || other.bottom <= first.y, `${width}: overlapping division controls`)
      }
    }
    if (width > 900) {
      const copyCenter = layout.copy.y + layout.copy.height / 2
      const visualCenter = layout.visual.y + layout.visual.height / 2
      assert.ok(Math.abs(copyCenter - visualCenter) < 2, `${width}: hero columns not centered`)
    }
    if (captureScreenshots) {
      // Rest the 3D render while capturing; software graphics otherwise races the screenshot.
      if (graphicsEnabled) {
        await evaluate(`document.querySelector('[aria-label="Pause visual animation"]')?.click()`)
        await waitFor(`document.querySelector('.rosette-hero__webgl canvas').dataset.animation === 'resting'`)
      }
      const screenshot = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width, height: layout.contentHeight, scale: 1 } })
      await fs.writeFile(path.join(artifacts, `welcome-${width}x${height}.png`), Buffer.from(screenshot.data, 'base64'))
    }
    results.push({ width, height, contentHeight: layout.contentHeight, checks: 'alignment, overflow, cube faces, control bounds, touch targets' })
  }
  if (graphicsEnabled) {
    await evaluate(`document.querySelector('[aria-label="Resume visual animation"]').click()`)
    for (let sample = 0; sample < 40; sample++) {
      const valid = await evaluate(`(() => {
        const scene = document.querySelector('.rosette-hero__scene').getBoundingClientRect();
        const visible = [...document.querySelectorAll('.rosette-hero__division')].filter(button => getComputedStyle(button).visibility === 'visible').map(button => button.getBoundingClientRect());
        return visible.every((b, index) => b.x >= scene.x - 1 && b.right <= scene.right + 1 && b.y >= scene.y - 1 && b.bottom <= scene.bottom + 1 && visible.slice(index + 1).every(other => b.right <= other.x || other.right <= b.x || b.bottom <= other.y || other.bottom <= b.y));
      })()`)
      assert.ok(valid, 'Moving division labels clipped or overlapped at phone width')
      await delay(90)
    }
    await evaluate(`document.querySelector('[aria-label="Pause visual animation"]').click()`)
    await evaluate(`document.querySelector('[aria-label="Reset 3D view"]').click()`)
    await waitFor(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.extension) > .99`)
  }
  // Real pointer input selects a division, and the selection can be cleared.
  await evaluate(`document.querySelector('[aria-label^="Explore DRONE"]').scrollIntoView({ block: 'center' })`)
  const drone = await evaluate(`(() => { const r = document.querySelector('[aria-label^="Explore DRONE"]').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } })()`)
  await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', ...drone, button: 'left', clickCount: 1 })
  await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', ...drone, button: 'left', clickCount: 1 })
  assert.ok(await evaluate(`document.querySelector('#rosette-division-detail').textContent.includes('DRONE')`), 'Selecting DRONE did not update detail')
  assert.equal(await evaluate(`document.querySelector('[aria-label^="Explore DRONE"]').getAttribute('aria-pressed')`), 'true')
  await evaluate(`document.querySelector('[aria-label^="Explore DRONE"]').click()`)
  assert.ok(await evaluate(`document.querySelector('#rosette-division-detail').textContent.includes('NakshaTech')`))
  if (graphicsEnabled) {
    await evaluate(`document.querySelector('.rosette-hero__scene').scrollIntoView({ block: 'center' })`)
    const cubePoint = await evaluate(`(() => { const r = document.querySelector('[aria-label^="Explore GIS"]').getBoundingClientRect(); const scene = document.querySelector('.rosette-hero__scene').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 - scene.height * .09 } })()`)
    await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', ...cubePoint })
    await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', ...cubePoint, button: 'left', clickCount: 1 })
    await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', ...cubePoint, button: 'left', clickCount: 1 })
    await waitFor(`document.querySelector('[aria-label^="Explore GIS"]').getAttribute('aria-pressed') === 'true'`)
    await evaluate(`document.querySelector('[aria-label^="Explore GIS"]').click()`)
  }
  await evaluate(`document.querySelector('[aria-label^="Explore GIS"]').focus()`)
  await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: ' ', code: 'Space', windowsVirtualKeyCode: 32 })
  await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: ' ', code: 'Space', windowsVirtualKeyCode: 32 })
  assert.equal(await evaluate(`document.querySelector('[aria-label^="Explore GIS"]').getAttribute('aria-pressed')`), 'true', 'Keyboard selection failed')
  if (graphicsEnabled) {
    await evaluate(`document.querySelector('.rosette-hero__scene').scrollIntoView({ block: 'center' })`)
    const scenePoint = await evaluate(`(() => { const r = document.querySelector('.rosette-hero__scene').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } })()`)
    const startYaw = await evaluate(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.viewYaw)`)
    await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', ...scenePoint })
    await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', ...scenePoint, button: 'left', clickCount: 1 })
    await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: scenePoint.x + 70, y: scenePoint.y + 12, button: 'left', buttons: 1 })
    await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', x: scenePoint.x + 70, y: scenePoint.y + 12, button: 'left', clickCount: 1 })
    await delay(200)
    const endYaw = await evaluate(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.viewYaw)`)
    assert.ok(Math.abs(endYaw - startYaw) > .1, 'Dragging did not rotate the 3D scene')
    await evaluate(`document.querySelector('[aria-label="Reset 3D view"]').click()`)
    await delay(50)
    assert.ok(Math.abs(await evaluate(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.viewYaw)`) + .06) < .015, 'Reset did not restore the view')
    await evaluate(`document.querySelector('.rosette-hero__scene').focus()`)
    await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 })
    await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 })
    await waitFor(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.viewYaw) > .02`)
  }
  await evaluate(`document.querySelector('[aria-label="Pause visual animation"]')?.click()`)
  assert.ok(await evaluate(`[...document.querySelectorAll('.rosette-hero__signal, .rosette-hero__satellite, .rosette-hero__hub-float')].every(element => getComputedStyle(element).animationPlayState === 'paused')`), 'Pause did not stop the animation')
  if (graphicsEnabled) assert.equal(await evaluate(`document.querySelector('.rosette-hero__webgl canvas').dataset.animation`), 'resting')
  if (graphicsEnabled) {
    const beforeTouch = await evaluate(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.viewYaw)`)
    const point = await evaluate(`(() => { const r = document.querySelector('.rosette-hero__scene').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } })()`)
    await cdp('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 })
    await cdp('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ ...point, id: 0 }] })
    await cdp('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: point.x + 60, y: point.y, id: 0 }] })
    await cdp('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await cdp('Emulation.setTouchEmulationEnabled', { enabled: false })
    const afterTouch = await evaluate(`Number(document.querySelector('.rosette-hero__webgl canvas').dataset.viewYaw)`)
    assert.ok(Math.abs(afterTouch - beforeTouch) > .1, 'Touch swipe did not rotate the scene')
    assert.ok(await evaluate(`(() => { const r = document.querySelector('.rosette-hero__scene').getBoundingClientRect(); return [...document.querySelectorAll('.rosette-hero__division')].every(button => { const b = button.getBoundingClientRect(); return b.x >= r.x && b.right <= r.right && b.y >= r.y && b.bottom <= r.bottom }) })()`), 'Labels clipped after touch rotation')
  }
  await evaluate(`document.querySelector('[aria-label="Resume visual animation"]').click()`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="Pause visual animation"]').getAttribute('aria-pressed')`), 'false')
  await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] })
  await waitFor(`!document.querySelector('[aria-label="Pause visual animation"]')`)
  assert.ok(await evaluate(`[...document.querySelectorAll('.rosette-hero__signal, .rosette-hero__satellite, .rosette-hero__hub-float')].every(element => getComputedStyle(element).animationName === 'none')`), 'Reduced motion did not stop all visual animation')
  // Tab navigation starts at the skip link, and Enter reaches the main content.
  await cdp('Page.navigate', { url })
  await waitFor(`document.querySelectorAll('.rosette-hero__division').length === 6`)
  await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 })
  await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 })
  assert.equal(await evaluate(`document.activeElement.className`), 'space-welcome__skip', 'Skip link is not first keyboard target')
  await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 })
  await waitFor(`document.activeElement.id === 'workspace-welcome'`)
  assert.deepEqual(errors, [], 'Welcome page browser errors detected')
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false })
  await delay(100)
  const welcomeTheme = await evaluate(`({ title: getComputedStyle(document.querySelector('.space-welcome__title-gradient')).backgroundImage, button: getComputedStyle(document.querySelector('.space-welcome__login')).backgroundImage, brandWidth: document.querySelector('.space-welcome__brand img').getBoundingClientRect().width })`)
  await evaluate(`document.querySelector('.space-welcome__login').click()`)
  await waitFor(`location.pathname === '/login' && document.querySelector('input[type="password"]')`)
  if (graphicsEnabled) {
    await waitFor(`document.querySelector('.naksha-login-globe-stage canvas')?.width > 0`)
    assert.equal(await evaluate(`Boolean(document.querySelector('.naksha-login-globe-fallback'))`), false, 'Supported WebGL should render the globe')
  } else {
    await waitFor(`document.querySelector('.naksha-login-globe-fallback')`)
  }
  assert.ok(await evaluate(`document.querySelector('form').textContent.includes('Welcome Back')`), 'Login form must remain available without WebGL')
  const loginTheme = await evaluate(`({ title: getComputedStyle(document.querySelector('.final-login-copy h1 strong')).backgroundImage, button: getComputedStyle(document.querySelector('.final-login-submit')).backgroundImage, brandWidth: document.querySelector('.final-login-brand img').getBoundingClientRect().width })`)
  assert.deepEqual(welcomeTheme, loginTheme, 'Welcome theme must match the existing login')
  assert.deepEqual(errors, [], 'Browser errors detected')
  const report = { url, graphicsEnabled, results, motionSamples, interactions: ['Organization Improvement Process heading', 'other copy preserved', 'login gradients and branding matched', 'pointer selection and clear', 'keyboard division selection', ...(graphicsEnabled ? ['Originkit expand / rotate / collapse loop', 'labels follow sub-cubes and hide when collapsed', 'pause freezes loop time', 'direct 3D cube selection', 'drag rotation', 'touch swipe', 'labels stay in bounds after rotation', 'reset view', 'keyboard 3D rotation'] : []), 'pause and resume', 'live reduced motion', 'keyboard skip link', graphicsEnabled ? 'login navigation and WebGL globe' : 'login navigation and WebGL fallback'], browserErrors: errors }
  await fs.writeFile(path.join(artifacts, 'report.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close()
  browser.kill()
  await delay(200)
  // profile is a fixed-prefix temporary directory created above, never a user path.
  await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }).catch(() => {})
}
