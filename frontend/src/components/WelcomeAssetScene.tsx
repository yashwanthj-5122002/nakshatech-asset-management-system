import { useEffect, useRef } from 'react'
// @ts-ignore - Three.js is the existing renderer used by react-globe.gl.
import * as THREE from 'three'

export interface AssetNodePosition { key: string; x: number; y: number; depth?: number; opacity?: number }
interface Props {
  paused: boolean
  reducedMotion: boolean
  selected: string | null
  highlighted: string | null
  resetVersion: number
  onReady: (ready: boolean) => void
  onProject: (positions: AssetNodePosition[]) => void
  onHighlight: (key: string | null) => void
  onSelect: (key: string) => void
}

// NATURAL_ORBIT_V2: true 3D depth staggering, no billboard or forced spacing.
// Opposite satellites balance the composition; slight depth offsets allow
// realistic perspective overlap instead of a flat edge-on line at 90 degrees.
const nodes = [
  { key: 'gis', arm: [0, 1, 0], label: 'GIS /\nMOBILE MAPPING' },
  { key: 'ortho', arm: [0.82, 0.53, -0.48], label: 'LASER\nSCANNING' },
  { key: 'drone', arm: [0.82, -0.53, -0.28], label: 'SOFTWARE\nTEAM' },
  { key: 'survey', arm: [0, -1, 0], label: 'PHOTOGRAMMETRY\n& SURVEY' },
  { key: 'civil', arm: [-0.82, -0.53, 0.48], label: 'CIVIL' },
  { key: 'lidar', arm: [-0.82, 0.53, 0.28], label: 'LiDAR\n& ORTHO' },
]

// NAKSHA_TRACKBALL_XY_V1: free 360-degree drag on X and Y (quaternion), plus press-to-spin.
// Motion adapted from the user's supplied Originkit Metal Rosette component.
const CYCLE_SECONDS = 3.45
// Hold the left mouse button to spin around the upright center axis.
const HOLD_TO_SPIN_DELAY_MS = 220
const HOLD_SECONDS_PER_REVOLUTION = 3.2
// When untouched, the entire globe turns slowly; after an interaction it rests briefly.
const IDLE_SECONDS_PER_REVOLUTION = 18
const IDLE_RESUME_DELAY_MS = 0
const MAX_COAST_RADIANS_PER_SECOND = 1.8
const DRAG_THRESHOLD_PX = 8
const DRAG_RADIANS_PER_PIXEL = (Math.PI * 2) / 520
const HOLD = .48
const START_PHASE = (1 - HOLD) * (.4 + .31) + HOLD / 2
function armExtension(cycle: number): number {
  const phase = cycle - Math.floor(cycle)
  const rest = (1 - HOLD) * .4
  const expand = (1 - HOLD) * .31
  const collapse = (1 - HOLD) * .29
  if (phase < rest) return 0
  if (phase < rest + expand) return 1 - Math.pow(1 - (phase - rest) / expand, 3)
  if (phase < rest + expand + HOLD) return 1
  return 1 - Math.pow(Math.min((phase - rest - expand - HOLD) / collapse, 1), 3)
}

/** Real 3D geometry; projected HTML controls stay attached to the same render frame. */
export default function WelcomeAssetScene(props: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const latest = useRef(props)
  const invalidate = useRef<(() => void) | null>(null)
  latest.current = props
  useEffect(() => { invalidate.current?.() }, [props.paused, props.reducedMotion, props.selected, props.highlighted, props.resetVersion])

  useEffect(() => {
    const canvas = canvasRef.current
    const host = canvas?.parentElement
    const interaction = host?.parentElement
    if (!canvas || !host || !interaction) return
    let renderer: any
    try {
      const context = canvas.getContext('webgl2', { alpha: true, antialias: true, powerPreference: 'low-power' })
      if (!context) { latest.current.onReady(false); return }
      renderer = new THREE.WebGLRenderer({ canvas, context, alpha: true, antialias: true })
    } catch { latest.current.onReady(false); return }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.setClearColor(0x000000, 0)
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(34, 1, .1, 60)
    camera.position.set(0, 0, 13)
    camera.lookAt(0, 0, 0)
    scene.add(new THREE.AmbientLight(0x63b9eb, 1.1))
    const keyLight = new THREE.DirectionalLight(0xbef9ff, 2.3)
    keyLight.position.set(-4, 6, 5)
    scene.add(keyLight)
    const blueLight = new THREE.PointLight(0x006dff, 35, 20)
    blueLight.position.set(4, -2, 4)
    scene.add(blueLight)
    const cyanLight = new THREE.PointLight(0x03cfee, 20, 15)
    cyanLight.position.set(-3, 2, 3)
    scene.add(cyanLight)

    const constellation = new THREE.Group()
    scene.add(constellation)
    const rosetteView = new THREE.Group()
    rosetteView.rotation.set(THREE.MathUtils.degToRad(17), -Math.PI / 5, 0)
    const rosette = new THREE.Group()
    rosetteView.add(rosette)
    constellation.add(rosetteView)
    const disposables: any[] = []
    const track = (object: any) => { disposables.push(object); return object }
    // Real 3D labels, attached to all six faces so they follow every rotation.
    // CanvasTexture avoids additional dependencies, and all GPU resources are disposed below.

    // Logo + matching department name on every face of all seven cubes.
    const addFaceLabels = (group: any, size: number, label: string, isHub: boolean) => {
      const side = 1024
      const canvas = document.createElement('canvas')
      canvas.width = side
      canvas.height = side
      const ctx = canvas.getContext('2d')!
      const texture = track(new THREE.CanvasTexture(canvas))
      texture.colorSpace = THREE.SRGBColorSpace
      texture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy())
      const logo = new Image()
      let alive = true

      const draw = () => {
        if (!alive) return
        ctx.clearRect(0, 0, side, side)
        ctx.strokeStyle = 'rgba(108, 240, 212, 0.20)'
        ctx.lineWidth = 4
        ctx.strokeRect(66, 66, 892, 892)
        ctx.strokeStyle = 'rgba(140, 245, 221, 0.64)'
        ctx.lineWidth = 6
        const a = 94, b = 930, leg = 95
        ctx.beginPath()
        ctx.moveTo(a, a + leg); ctx.lineTo(a, a); ctx.lineTo(a + leg, a)
        ctx.moveTo(b - leg, a); ctx.lineTo(b, a); ctx.lineTo(b, a + leg)
        ctx.moveTo(a, b - leg); ctx.lineTo(a, b); ctx.lineTo(a + leg, b)
        ctx.moveTo(b - leg, b); ctx.lineTo(b, b); ctx.lineTo(b, b - leg)
        ctx.stroke()

        // Preserve image aspect ratio. The logo is the hero on the center cube
        // and has a fixed upper slot on every smaller department cube.
        if (logo.complete && logo.naturalWidth > 0 && logo.naturalHeight > 0) {
          const maxWidth = isHub ? 780 : 740
          const maxHeight = isHub ? 220 : 175
          const scale = Math.min(maxWidth / logo.naturalWidth, maxHeight / logo.naturalHeight)
          const w = logo.naturalWidth * scale
          const h = logo.naturalHeight * scale
          const centerY = isHub ? 490 : 315
          ctx.drawImage(logo, (side - w) / 2, centerY - h / 2, w, h)
        }

        // Department text stays readable and is centered below the logo.
        // On the hub, the text is a fallback if the image failed to load.
        if (!isHub || !(logo.complete && logo.naturalWidth > 0)) {
          const lines = label.split('\n')
          const baseSize = isHub ? 126 : 114
          ctx.font = `600 ${baseSize}px "Segoe UI", Arial, sans-serif`
          const widest = Math.max(1, ...lines.map(line => ctx.measureText(line).width))
          const fontSize = baseSize * Math.min(1, 820 / widest)
          ctx.font = `600 ${fontSize}px "Segoe UI", Arial, sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.lineJoin = 'round'
          ctx.shadowBlur = 0
          ctx.strokeStyle = 'rgba(0, 8, 15, 0.87)'
          ctx.lineWidth = 7
          ctx.fillStyle = '#eff9f8'
          const lineHeight = fontSize * 1.22
          const centerY = isHub ? 530 : 685
          const firstY = centerY - (lines.length - 1) * lineHeight / 2
          lines.forEach((line, index) => {
            const y = firstY + index * lineHeight
            ctx.strokeText(line, side / 2, y)
            ctx.fillText(line, side / 2, y)
          })
          if (!isHub) {
            ctx.beginPath()
            ctx.moveTo(438, 845); ctx.lineTo(586, 845)
            ctx.strokeStyle = 'rgba(113, 239, 215, 0.82)'
            ctx.lineWidth = 5
            ctx.stroke()
          }
        }
        texture.needsUpdate = true
        invalidate.current?.()
      }
      // A single image per cube feeds the SAME texture on all six faces.
      logo.onload = draw
      logo.onerror = draw
      logo.src = '/nakshatech-horizontal-light.png'
      draw()
      // Release event callbacks at unmount to avoid updating disposed textures.
      track({ dispose: () => { alive = false; logo.onload = null; logo.onerror = null } })

      const geometry = track(new THREE.PlaneGeometry(size * 0.985, size * 0.985))
      const material = track(new THREE.MeshBasicMaterial({
        map: texture, transparent: true, depthWrite: false, toneMapped: false,
        side: THREE.FrontSide, polygonOffset: true, polygonOffsetFactor: -1,
      }))
      const d = size * 0.505
      const faces: Array<[number, number, number, number, number, number]> = [
        [0, 0, d, 0, 0, 0], [0, 0, -d, 0, Math.PI, 0],
        [d, 0, 0, 0, Math.PI / 2, 0], [-d, 0, 0, 0, -Math.PI / 2, 0],
        [0, d, 0, -Math.PI / 2, 0, 0], [0, -d, 0, Math.PI / 2, 0, 0],
      ]
      faces.forEach(([x, y, z, rx, ry, rz]) => {
        const face = new THREE.Mesh(geometry, material)
        face.position.set(x, y, z)
        face.rotation.set(rx, ry, rz)
        group.add(face)
      })
    }

    const makeCube = (size: number, hub = false, label = '') => {
      const group = new THREE.Group()
      const geometry = track(new THREE.BoxGeometry(size, size, size))
      const material = track(new THREE.MeshStandardMaterial({
        color: hub ? 0x06162e : 0x04162b,
        metalness: .24,
        roughness: .43,
        emissive: hub ? 0x000f22 : 0x000b1c,
        emissiveIntensity: .28,
        transparent: false,
        opacity: 1,
        depthWrite: true,
      }))
      const mesh = new THREE.Mesh(geometry, material)
      group.add(mesh)
      const edges = track(new THREE.EdgesGeometry(geometry))
      const edgeMaterial = track(new THREE.LineBasicMaterial({ color: hub ? 0x48badb : 0x2684ad, transparent: true, opacity: .64 }))
      group.add(new THREE.LineSegments(edges, edgeMaterial))
      // Fine circuit lines on the front face give each solid volume an illuminated surface.
      const circuitVertices = new Float32Array([
        -size * .34, size * .27, size * .503, size * .12, size * .27, size * .503,
        size * .12, size * .27, size * .503, size * .12, size * .1, size * .503,
        size * .12, size * .1, size * .503, size * .34, size * .1, size * .503,
        -size * .34, -size * .28, size * .503, size * .34, -size * .28, size * .503,
      ])
      const circuit = track(new THREE.BufferGeometry())
      circuit.setAttribute('position', new THREE.BufferAttribute(circuitVertices, 3))
      group.add(new THREE.LineSegments(circuit, track(new THREE.LineBasicMaterial({ color: 0x228ab3, transparent: true, opacity: .34 }))))
      if (label) addFaceLabels(group, size, label, hub)
      group.rotation.set(0, 0, 0)
      return { group, material, edgeMaterial }
    }
    const hub = makeCube(1.55, true, 'NAKSHATECH')
    rosette.add(hub.group)
    let disposed = false


    const glowCanvas = document.createElement('canvas')
    glowCanvas.width = glowCanvas.height = 128
    const glowContext = glowCanvas.getContext('2d')!
    const gradient = glowContext.createRadialGradient(64, 64, 0, 64, 64, 64)
    gradient.addColorStop(0, '#087baa66')
    gradient.addColorStop(.23, '#07507744')
    gradient.addColorStop(1, '#00204000')
    glowContext.fillStyle = gradient
    glowContext.fillRect(0, 0, 128, 128)
    const glowTexture = track(new THREE.CanvasTexture(glowCanvas))
    const glow = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: glowTexture, transparent: true, opacity: .17, blending: THREE.AdditiveBlending, depthWrite: false })))
    glow.scale.set(6, 6, 1)
    glow.position.z = -.8
    constellation.add(glow)

    const dotGeometry = track(new THREE.SphereGeometry(.035, 8, 8))
    const dotMaterial = track(new THREE.MeshBasicMaterial({ color: 0x7aeeff }))
    const satellites = nodes.map(({ key, arm, label }, index) => {
      const cube = makeCube(.78, false, label)
      const origin = new THREE.Vector3(...arm).multiplyScalar(3.1)
      cube.group.position.copy(origin)
      rosette.add(cube.group)
      const lineGeometry = track(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), origin]))
      const lineMaterial = track(new THREE.LineBasicMaterial({ color: 0x0875ad, transparent: true, opacity: .55 }))
      const line = new THREE.Line(lineGeometry, lineMaterial)
      rosette.add(line)
      const dot = new THREE.Mesh(dotGeometry, dotMaterial)
      rosette.add(dot)
      return { key, index, ...cube, origin, lineGeometry, lineMaterial, dot }
    })

    // Latitude and meridian curves create the same planetary depth as the login globe.
    const globeGrid = new THREE.Group()
    const gridMaterial = track(new THREE.LineBasicMaterial({ color: 0x1688c1, transparent: true, opacity: .12 }))
    for (let latitude = -60; latitude <= 60; latitude += 30) {
      const phi = latitude * Math.PI / 180
      const points = Array.from({ length: 129 }, (_, index) => {
        const theta = index / 128 * Math.PI * 2
        return new THREE.Vector3(3.5 * Math.cos(phi) * Math.cos(theta), 3.5 * Math.sin(phi), 3.5 * Math.cos(phi) * Math.sin(theta))
      })
      globeGrid.add(new THREE.Line(track(new THREE.BufferGeometry().setFromPoints(points)), gridMaterial))
    }
    for (let meridian = 0; meridian < 6; meridian++) {
      const theta = meridian / 6 * Math.PI
      const points = Array.from({ length: 129 }, (_, index) => {
        const phi = index / 128 * Math.PI * 2
        return new THREE.Vector3(3.5 * Math.cos(phi) * Math.cos(theta), 3.5 * Math.sin(phi), 3.5 * Math.cos(phi) * Math.sin(theta))
      })
      globeGrid.add(new THREE.Line(track(new THREE.BufferGeometry().setFromPoints(points)), gridMaterial))
    }
    constellation.add(globeGrid)

    let width = 1
    let height = 1
    let visible = true
    let contextAvailable = true
    let frame = 0
    let elapsed = 0
    let previousTime = performance.now()
    let lastReset = latest.current.resetVersion
    let resumeIdleAt = performance.now() + 800
    let coastYawSpeed = (Math.PI * 2) / IDLE_SECONDS_PER_REVOLUTION
    let coastPitchSpeed = 0
    let lastDragTime = performance.now()
    // Orientation is a unit quaternion, so full X/Y rotations never gimbal-lock.
    const orientation = new THREE.Quaternion()
    const axisX = new THREE.Vector3(1, 0, 0)
    const axisY = new THREE.Vector3(0, 1, 0)
    const turnX = new THREE.Quaternion()
    const turnY = new THREE.Quaternion()
    const orientationEuler = new THREE.Euler(0, 0, 0, 'YXZ')
    let dragging = false
    let manualDragging = false
    let holdSpinning = false
    let keyboardInspection = false
    let activePointerId: number | null = null
    let pressStartedAt = 0
    let previousX = 0
    let previousY = 0
    let pressX = 0
    let pressY = 0
    let pressedNode: string | null = null
    // Pre-multiplication applies each turn in the viewer's screen axes.
    // This is a virtual trackball, not clamped Euler pitch/yaw.
    const rotateByScreenAngles = (yawDelta: number, pitchDelta: number) => {
      turnX.setFromAxisAngle(axisX, pitchDelta)
      turnY.setFromAxisAngle(axisY, yawDelta)
      orientation.premultiply(turnX.multiply(turnY)).normalize()
    }
    const raycaster = new THREE.Raycaster()
    const pointerVector = new THREE.Vector2()
    const pick = (event: PointerEvent) => {
      const rect = interaction.getBoundingClientRect()
      pointerVector.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1)
      raycaster.setFromCamera(pointerVector, camera)
      const hit = raycaster.intersectObjects(satellites.map(node => node.group.children[0]), false)[0]
      return hit ? satellites.find(node => node.group.children[0] === hit.object)?.key ?? null : null
    }
    const labelPosition = new THREE.Vector3()
    const shouldAnimate = () => contextAvailable && visible && !document.hidden && !latest.current.paused && !latest.current.reducedMotion
    // Keep the render loop alive during a press even if the decorative animation was paused.
    // An explicit reduced-motion preference still disables automatic hold-to-spin.
    const canHoldSpin = () => dragging && !manualDragging && contextAvailable && visible && !document.hidden && !latest.current.reducedMotion
    const shouldRunLoop = () => shouldAnimate() || canHoldSpin()
    const inspecting = () => dragging || keyboardInspection || Boolean(latest.current.highlighted || latest.current.selected)
    const paint = () => {
      if (disposed || !contextAvailable) return
      if (lastReset !== latest.current.resetVersion) {
        lastReset = latest.current.resetVersion
        orientation.identity()
        elapsed = 0
        resumeIdleAt = performance.now()
        coastYawSpeed = (Math.PI * 2) / IDLE_SECONDS_PER_REVOLUTION
        coastPitchSpeed = 0
      }
      // Free X/Y trackball orientation; all scene elements rotate together.
      // One shared quaternion controls cubes, labels and globe grid.
      constellation.quaternion.copy(orientation)
      const extension = latest.current.reducedMotion || inspecting() ? 1 : armExtension(START_PHASE + elapsed / CYCLE_SECONDS)
      rosette.rotation.y = 0
      globeGrid.rotation.y = 0 // Wireframe rotates with the constellation
      for (const node of satellites) {
        const active = node.key === (latest.current.highlighted ?? latest.current.selected)
        node.group.position.copy(node.origin).multiplyScalar(extension)
        node.group.visible = extension > .05
        node.dot.visible = extension > .35
        node.lineMaterial.opacity = extension * (active ? 1 : .5)
        node.group.scale.setScalar(active ? 1.09 : 1)
        node.material.emissiveIntensity = active ? .58 : .28
        node.edgeMaterial.color.setHex(active ? 0x9cffff : 0x26bfea)
        const attribute = node.lineGeometry.getAttribute('position')
        attribute.setXYZ(1, node.group.position.x, node.group.position.y, node.group.position.z)
        attribute.needsUpdate = true
        const progress = ((elapsed * .22 + node.index / 6) % 1)
        node.dot.position.copy(node.group.position).multiplyScalar(progress)
      }
      scene.updateMatrixWorld(true)
      latest.current.onProject(satellites.map(node => {
        node.group.getWorldPosition(labelPosition)
        labelPosition.y -= .8
        labelPosition.project(camera)
        return {
          key: node.key, x: (labelPosition.x + 1) / 2 * 100, y: (1 - labelPosition.y) / 2 * 100,
          depth: labelPosition.z, opacity: Math.max(0, Math.min(1, (extension - .72) / .18)),
        }
      }))
      renderer.render(scene, camera)
      orientationEuler.setFromQuaternion(orientation, 'YXZ')
      canvas.dataset.viewYaw = orientationEuler.y.toFixed(4)
      canvas.dataset.viewPitch = orientationEuler.x.toFixed(4)
      canvas.dataset.animation = shouldAnimate() ? 'running' : 'resting'
      canvas.dataset.extension = extension.toFixed(4)
      canvas.dataset.spin = orientationEuler.y.toFixed(4)
    }
    const loop = (time: number) => {
      frame = 0
      // Cap rendering at approximately 30 fps to stay responsive on smaller devices.
      if (time - previousTime >= 32) {
        const deltaSeconds = Math.min((time - previousTime) / 1000, .1)
        if (shouldAnimate()) elapsed += deltaSeconds
        if (canHoldSpin() && time - pressStartedAt >= HOLD_TO_SPIN_DELAY_MS) {
          // Hold: one exact full revolution per HOLD_SECONDS_PER_REVOLUTION.
          holdSpinning = true
          rotateByScreenAngles(deltaSeconds * (Math.PI * 2 / HOLD_SECONDS_PER_REVOLUTION), 0)
        } else if (shouldAnimate() && !dragging && time >= resumeIdleAt) {
          // Continue rotating along the last manual X/Y drag, even after the pointer leaves.
          rotateByScreenAngles(deltaSeconds * coastYawSpeed, deltaSeconds * coastPitchSpeed)
        }
        previousTime = time
        paint()
      }
      if (shouldRunLoop()) frame = requestAnimationFrame(loop)
    }
    const sync = () => {
      if (frame) cancelAnimationFrame(frame)
      frame = 0
      previousTime = performance.now()
      paint()
      if (shouldRunLoop()) frame = requestAnimationFrame(loop)
    }
    invalidate.current = sync
    const resize = () => {
      const rect = host.getBoundingClientRect()
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.position.z = width < 600 ? 14 : 13
      camera.updateProjectionMatrix()
      sync()
    }
    // Quaternion-based virtual trackball: drag in X, Y or both, without angle limits.
    const move = (event: PointerEvent) => {
      if (dragging && event.pointerId === activePointerId) {
        const dx = event.clientX - previousX
        const dy = event.clientY - previousY
        const travelled = Math.hypot(event.clientX - pressX, event.clientY - pressY)
        if (travelled >= DRAG_THRESHOLD_PX && !manualDragging) {
          manualDragging = true
          holdSpinning = false
        }
        if (manualDragging) {
          // Apply rotation in screen space so movement still feels natural
          // after turning the globe upside down or all the way around.
          rotateByScreenAngles(dx * DRAG_RADIANS_PER_PIXEL, dy * DRAG_RADIANS_PER_PIXEL)
          const now = performance.now()
          const dt = Math.max((now - lastDragTime) / 1000, 1 / 60)
          if (dx !== 0 || dy !== 0) {
            coastYawSpeed = THREE.MathUtils.clamp(
              dx * DRAG_RADIANS_PER_PIXEL / dt,
              -MAX_COAST_RADIANS_PER_SECOND, MAX_COAST_RADIANS_PER_SECOND
            )
            coastPitchSpeed = THREE.MathUtils.clamp(
              dy * DRAG_RADIANS_PER_PIXEL / dt,
              -MAX_COAST_RADIANS_PER_SECOND, MAX_COAST_RADIANS_PER_SECOND
            )
          }
          lastDragTime = now
          // When the decorative loop is paused, redraw on each pointer move.
          if (!shouldAnimate()) paint()
        }
        previousX = event.clientX
        previousY = event.clientY
      }
      if (!dragging && !(event.target as Element).closest('button')) {
        latest.current.onHighlight(pick(event))
      }
    }
    const down = (event: PointerEvent) => {
      if (dragging || event.button !== 0 || (event.target as Element).closest('button')) return
      dragging = true
      manualDragging = false
      holdSpinning = false
      // Mouse input takes over from idle movement without resetting orientation.
      resumeIdleAt = Number.POSITIVE_INFINITY
      lastDragTime = performance.now()
      activePointerId = event.pointerId
      pressStartedAt = performance.now()
      previousX = event.clientX
      previousY = event.clientY
      pressX = event.clientX
      pressY = event.clientY
      pressedNode = pick(event)
      interaction.setPointerCapture(event.pointerId)
      interaction.classList.add('is-dragging')
      sync()
    }
    const up = (event: PointerEvent) => {
      if (!dragging || event.pointerId !== activePointerId) return
      const selectedNode = pressedNode
      const longPress = !latest.current.reducedMotion && performance.now() - pressStartedAt >= HOLD_TO_SPIN_DELAY_MS
      const isClick = event.type === 'pointerup' && !manualDragging && !holdSpinning && !longPress &&
        Math.hypot(event.clientX - pressX, event.clientY - pressY) < DRAG_THRESHOLD_PX
      // Keep the automatic hold-spin speed after release, too.
      if (holdSpinning) {
        coastYawSpeed = (Math.PI * 2) / HOLD_SECONDS_PER_REVOLUTION
        coastPitchSpeed = 0
      }
      dragging = false
      manualDragging = false
      holdSpinning = false
      activePointerId = null
      resumeIdleAt = performance.now() + IDLE_RESUME_DELAY_MS
      pressedNode = null
      if (interaction.hasPointerCapture(event.pointerId)) interaction.releasePointerCapture(event.pointerId)
      interaction.classList.remove('is-dragging')
      sync()
      if (isClick && selectedNode) latest.current.onSelect(selectedNode)
    }
    const lostCapture = (event: PointerEvent) => {
      // Prevent a stuck spin if a window/app transition breaks pointer capture.
      if (dragging && event.pointerId === activePointerId) up(event)
    }
    const leave = () => {
      latest.current.onHighlight(null)
      // Leaving the scene never stops the continuous X/Y rotation.
      resumeIdleAt = performance.now()
    }
    const keydown = (event: KeyboardEvent) => {
      if (event.target !== interaction || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
      event.preventDefault()
      const step = Math.PI / 12
      if (event.key === 'ArrowLeft') rotateByScreenAngles(-step, 0)
      if (event.key === 'ArrowRight') rotateByScreenAngles(step, 0)
      if (event.key === 'ArrowUp') rotateByScreenAngles(0, -step)
      if (event.key === 'ArrowDown') rotateByScreenAngles(0, step)
      resumeIdleAt = performance.now() + IDLE_RESUME_DELAY_MS
      if (!shouldAnimate()) paint()
    }
    const focus = (event: FocusEvent) => {
      if (event.target === interaction) { keyboardInspection = true; sync() }
    }
    const blur = (event: FocusEvent) => {
      if (!interaction.contains(event.relatedTarget as Node | null)) { keyboardInspection = false; sync() }
    }
    const contextLost = (event: Event) => {
      event.preventDefault()
      contextAvailable = false
      if (frame) cancelAnimationFrame(frame)
      frame = 0
      latest.current.onReady(false)
    }
    const contextRestored = () => { contextAvailable = true; latest.current.onReady(true); sync() }
    const observer = new ResizeObserver(resize)
    const visibility = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() })
    observer.observe(host)
    visibility.observe(host)
    interaction.addEventListener('pointerdown', down)
    interaction.addEventListener('pointermove', move)
    interaction.addEventListener('pointerup', up)
    interaction.addEventListener('pointercancel', up)
    interaction.addEventListener('lostpointercapture', lostCapture)
    interaction.addEventListener('pointerleave', leave)
    interaction.addEventListener('keydown', keydown)
    interaction.addEventListener('focusin', focus)
    interaction.addEventListener('focusout', blur)
    canvas.addEventListener('webglcontextlost', contextLost)
    canvas.addEventListener('webglcontextrestored', contextRestored)
    document.addEventListener('visibilitychange', sync)
    resize()
    latest.current.onReady(true)
    return () => {
      disposed = true
      invalidate.current = null
      if (frame) cancelAnimationFrame(frame)
      observer.disconnect()
      visibility.disconnect()
      interaction.removeEventListener('pointerdown', down)
      interaction.removeEventListener('pointermove', move)
      interaction.removeEventListener('pointerup', up)
      interaction.removeEventListener('pointercancel', up)
      interaction.removeEventListener('lostpointercapture', lostCapture)
      interaction.removeEventListener('pointerleave', leave)
      interaction.removeEventListener('keydown', keydown)
      interaction.removeEventListener('focusin', focus)
      interaction.removeEventListener('focusout', blur)
      canvas.removeEventListener('webglcontextlost', contextLost)
      canvas.removeEventListener('webglcontextrestored', contextRestored)
      document.removeEventListener('visibilitychange', sync)
      disposables.forEach(object => object.dispose())
      renderer.dispose()
    }
  }, [])

  return <div className="rosette-hero__webgl" aria-hidden="true"><canvas ref={canvasRef} /></div>
}
