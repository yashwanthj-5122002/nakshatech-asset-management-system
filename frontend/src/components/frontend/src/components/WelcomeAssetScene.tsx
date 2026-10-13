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

const nodes = [
  { key: 'gis', arm: [0, 1, 0], label: 'GIS /\nMOBILE MAPPING' },
  { key: 'ortho', arm: [0, 0, -1], label: 'LASER\nSCANNING' },
  { key: 'drone', arm: [1, 0, 0], label: 'SOFTWARE\nTEAM' },
  { key: 'survey', arm: [0, -1, 0], label: 'PHOTOGRAMMETRY\n& SURVEY' },
  { key: 'civil', arm: [0, 0, 1], label: 'CIVIL' },
  { key: 'lidar', arm: [-1, 0, 0], label: 'LiDAR\n& ORTHO' },
]
// GRAPHITE + MINT THEME
// Change these values whenever you want to experiment.
const CUBE_THEME = {
  hub: 0x10212b,          // Main NAKSHATECH cube
  satellite: 0x0d242d,    // Six smaller cubes
  emissive: 0x062a2b,     // Subtle internal reflection
  rim: 0x63e6d0,          // Mint cube borders
  activeRim: 0xa3fff0,    // Selected cube border
  halo: 0x41ddca,         // Outer edge halo
  corners: 0x9bffeb,      // Illuminated corner points
  connection: 0x44bfb9,   // Connecting lines
  particle: 0x91eedf,     // Animated dots
  globe: 0x3292a0,        // Planetary grid lines
} as const
// Motion adapted from the user's supplied Originkit Metal Rosette component.
const CYCLE_SECONDS = 3.45
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
    camera.position.set(0, .25, 13)
    camera.lookAt(0, 0, 0)
    scene.add(new THREE.AmbientLight(0x63b9eb, 2.3))
    const keyLight = new THREE.DirectionalLight(0xbef9ff, 4.2)
    keyLight.position.set(-4, 6, 5)
    scene.add(keyLight)
    const blueLight = new THREE.PointLight(0x006dff, 75, 20)
    blueLight.position.set(4, -2, 4)
    scene.add(blueLight)
    const cyanLight = new THREE.PointLight(0x03cfee, 45, 15)
    cyanLight.position.set(-3, 2, 3)
    scene.add(cyanLight)

    const constellation = new THREE.Group()
    scene.add(constellation)
    const rosetteView = new THREE.Group()
    rosetteView.rotation.set(0, -Math.PI / 5, 0)
    const rosette = new THREE.Group()
    rosetteView.add(rosette)
    constellation.add(rosetteView)
    const disposables: any[] = []
    const track = (object: any) => { disposables.push(object); return object }
    // Real 3D labels, attached to all six faces so they follow every rotation.
    // CanvasTexture avoids additional dependencies, and all GPU resources are disposed below.
    // Creates the text and decorative details on all six cube faces.
// NakshaTech logo + department name on all six cube faces.
const addFaceLabels = (
  group: any,
  size: number,
  label: string,
  isHub: boolean
) => {
  const canvas = document.createElement('canvas')
  const side = 1024

  canvas.width = side
  canvas.height = side

  const ctx = canvas.getContext('2d')!

  // Use the existing logo in frontend/public.
  const logo = new Image()
  logo.src = '/nakshatech-horizontal-light.png'

  const drawFace = () => {
    ctx.clearRect(0, 0, side, side)

    // Subtle panel outline.
    ctx.strokeStyle = 'rgba(99, 230, 208, 0.18)'
    ctx.lineWidth = 4
    ctx.strokeRect(60, 60, 904, 904)

    // Decorative corner brackets.
    ctx.strokeStyle = 'rgba(125, 245, 225, 0.65)'
    ctx.lineWidth = 6

    const corners = [
      [90, 160, 90, 90, 160, 90],
      [864, 90, 934, 90, 934, 160],
      [90, 864, 90, 934, 160, 934],
      [864, 934, 934, 934, 934, 864],
    ]

    corners.forEach(([x1, y1, x2, y2, x3, y3]) => {
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.lineTo(x3, y3)
      ctx.stroke()
    })

    // Center the logo using its actual image proportions.
    if (logo.complete && logo.naturalWidth > 0) {
      const maxLogoWidth = isHub ? 760 : 700
      const maxLogoHeight = isHub ? 260 : 190

      const scale = Math.min(
        maxLogoWidth / logo.naturalWidth,
        maxLogoHeight / logo.naturalHeight
      )

      const logoWidth = logo.naturalWidth * scale
      const logoHeight = logo.naturalHeight * scale

      const logoX = (side - logoWidth) / 2
      const logoY = isHub
        ? (side - logoHeight) / 2
        : 265 - logoHeight / 2

      ctx.drawImage(
        logo,
        logoX,
        logoY,
        logoWidth,
        logoHeight
      )
    }

    // Central cube: the logo is the main content.
    // Satellite cubes: logo above department name.
    if (!isHub) {
      const lines = label.split('\n')
      const baseFont = lines.length > 1 ? 105 : 135

      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.font = `600 ${baseFont}px "Segoe UI", Arial, sans-serif`

      const widestLine = Math.max(
        1,
        ...lines.map(line => ctx.measureText(line).width)
      )

      const fontSize = baseFont * Math.min(
        1,
        820 / widestLine
      )

      ctx.font = `600 ${fontSize}px "Segoe UI", Arial, sans-serif`
      ctx.fillStyle = '#eef8fa'
      ctx.strokeStyle = 'rgba(0, 12, 20, 0.85)'
      ctx.lineWidth = 5
      ctx.lineJoin = 'round'
      ctx.shadowBlur = 0

      const lineHeight = fontSize * 1.25
      const centerY = 660
      const startY =
        centerY - ((lines.length - 1) * lineHeight) / 2

      lines.forEach((line, index) => {
        const y = startY + index * lineHeight

        ctx.strokeText(line, side / 2, y)
        ctx.fillText(line, side / 2, y)
      })

      // Subtle separation between logo and department.
      ctx.beginPath()
      ctx.moveTo(430, 450)
      ctx.lineTo(594, 450)
      ctx.strokeStyle = 'rgba(105, 239, 211, 0.65)'
      ctx.lineWidth = 5
      ctx.stroke()
    }
  }

  // The canvas is shared as the texture for all six faces.
  const texture = track(new THREE.CanvasTexture(canvas))
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = Math.min(
    4,
    renderer.capabilities.getMaxAnisotropy()
  )

  // Draw immediately, then redraw when the logo finishes loading.
  drawFace()
  texture.needsUpdate = true

  logo.onload = () => {
    drawFace()
    texture.needsUpdate = true
    invalidate.current?.()
  }

  // Allow the label to remain visible if the logo is unavailable.
  logo.onerror = () => {
    drawFace()
    texture.needsUpdate = true
    invalidate.current?.()
  }

  const faceGeometry = track(
    new THREE.PlaneGeometry(size * 0.98, size * 0.98)
  )

  const faceMaterial = track(new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    side: THREE.FrontSide,
    polygonOffset: true,
    polygonOffsetFactor: -1,
  }))

  // Six faces, all outward-facing.
  const d = size * 0.504

  const faces: Array<
    [number, number, number, number, number, number]
  > = [
    [0, 0, d, 0, 0, 0],                   // Front
    [0, 0, -d, 0, Math.PI, 0],           // Back
    [d, 0, 0, 0, Math.PI / 2, 0],        // Right
    [-d, 0, 0, 0, -Math.PI / 2, 0],      // Left
    [0, d, 0, -Math.PI / 2, 0, 0],       // Top
    [0, -d, 0, Math.PI / 2, 0, 0],       // Bottom
  ]

  faces.forEach(([x, y, z, rx, ry, rz]) => {
    const face = new THREE.Mesh(faceGeometry, faceMaterial)

    face.position.set(x, y, z)
    face.rotation.set(rx, ry, rz)

    group.add(face)
  })
}

    // Creates the solid cube, glowing edges and corner lights.
const makeCube = (
  size: number,
  hub = false,
  label = ''
) => {
  const group = new THREE.Group()

  // 1. Actual solid cube geometry.
  const geometry = track(
    new THREE.BoxGeometry(size, size, size)
  )

  // 2. Graphite metallic material.
  const material = track(new THREE.MeshStandardMaterial({
    color: hub ? CUBE_THEME.hub : CUBE_THEME.satellite,
    metalness: 0.35,
    roughness: 0.44,
    emissive: CUBE_THEME.emissive,
    emissiveIntensity: 0.18,
    transparent: false,
    opacity: 1,
    depthWrite: true,
  }))

  // Keep the physical cube as the FIRST group child.
  // This is important for your existing mouse raycasting.
  group.add(new THREE.Mesh(geometry, material))

  // 3. Crisp mint outlines.
  const edges = track(new THREE.EdgesGeometry(geometry))

  const edgeMaterial = track(new THREE.LineBasicMaterial({
    color: CUBE_THEME.rim,
    transparent: true,
    opacity: hub ? 1 : 0.93,
    depthWrite: false,
    toneMapped: false,
  }))

  group.add(new THREE.LineSegments(edges, edgeMaterial))

  // 4. Second, slightly larger outline for a soft halo.
  const haloMaterial = track(new THREE.LineBasicMaterial({
    color: CUBE_THEME.halo,
    transparent: true,
    opacity: 0.33,
    depthWrite: false,
    toneMapped: false,
  }))

  const halo = new THREE.LineSegments(edges, haloMaterial)
  halo.scale.setScalar(1.035)
  group.add(halo)

  // 5. Tiny illuminated points on all eight corners.
  const cornerGeometry = track(
    new THREE.SphereGeometry(size * 0.014, 8, 6)
  )

  const cornerMaterial = track(new THREE.MeshBasicMaterial({
    color: CUBE_THEME.corners,
    transparent: true,
    opacity: 0.77,
    toneMapped: false,
  }))

  for (const x of [-1, 1]) {
    for (const y of [-1, 1]) {
      for (const z of [-1, 1]) {
        const point = new THREE.Mesh(
          cornerGeometry,
          cornerMaterial
        )

        point.position.set(
          x * size * 0.5,
          y * size * 0.5,
          z * size * 0.5
        )

        group.add(point)
      }
    }
  }

  // 6. Attach the label to the six cube faces.
  if (label) {
    addFaceLabels(group, size, label, hub)
  }

  return { group, material, edgeMaterial }
}
    const hub = makeCube(1.55, true, 'NAKSHATECH')
    rosette.add(hub.group)
    let disposed = false
    

    const glowCanvas = document.createElement('canvas')
    glowCanvas.width = glowCanvas.height = 128
    const glowContext = glowCanvas.getContext('2d')!
    const gradient = glowContext.createRadialGradient(64, 64, 0, 64, 64, 64)
    gradient.addColorStop(0, 'rgb(6, 246, 218)')
gradient.addColorStop(.23, 'rgb(0, 213, 246)')
gradient.addColorStop(1, 'rgba(15, 184, 241, 0)')
    glowContext.fillStyle = gradient
    glowContext.fillRect(0, 0, 128, 128)
    const glowTexture = track(new THREE.CanvasTexture(glowCanvas))
    const glow = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: glowTexture, transparent: true, opacity: .25, blending: THREE.AdditiveBlending, depthWrite: false })))
    glow.scale.set(6, 6, 1)
    glow.position.z = -.8
    constellation.add(glow)

    const dotGeometry = track(new THREE.SphereGeometry(.035, 8, 8))
    const dotMaterial = track(new THREE.MeshBasicMaterial({
  color: CUBE_THEME.particle
}))

    const satellites = nodes.map(({ key, arm, label }, index) => {
  const cube = makeCube(.94, false, label)
      const origin = new THREE.Vector3(...arm).multiplyScalar(3.05)
      cube.group.position.copy(origin)
      rosette.add(cube.group)
      const lineGeometry = track(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), origin]))
      const lineMaterial = track(new THREE.LineBasicMaterial({
  color: CUBE_THEME.connection,
  transparent: true,
  opacity: 0.54
}))
      const line = new THREE.Line(lineGeometry, lineMaterial)
      rosette.add(line)
      const dot = new THREE.Mesh(dotGeometry, dotMaterial)
      rosette.add(dot)
      return { key, index, ...cube, origin, lineGeometry, lineMaterial, dot }
    })

    // Latitude and meridian curves create the same planetary depth as the login globe.
    const globeGrid = new THREE.Group()
   const gridMaterial = track(new THREE.LineBasicMaterial({
  color: CUBE_THEME.globe,
  transparent: true,
  opacity: 0.16
}))
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
    let yaw = -.06
    let pitch = .035
    let targetYaw = yaw
    let targetPitch = pitch
    let dragging = false
    let keyboardInspection = false
    let previousX = 0
    let previousY = 0
    let pressX = 0
    let pressY = 0
    let pressedNode: string | null = null
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
    const inspecting = () => dragging || keyboardInspection || Boolean(latest.current.highlighted || latest.current.selected)
    const paint = () => {
      if (disposed || !contextAvailable) return
      if (lastReset !== latest.current.resetVersion) {
        lastReset = latest.current.resetVersion
        targetYaw = yaw = -.06
        targetPitch = pitch = .035
        elapsed = 0
      }
      yaw += (targetYaw - yaw) * .2
      pitch += (targetPitch - pitch) * .2
      constellation.rotation.set(pitch, yaw, 0)
      const extension = latest.current.reducedMotion || inspecting() ? 1 : armExtension(START_PHASE + elapsed / CYCLE_SECONDS)
      const spin = latest.current.reducedMotion || keyboardInspection ? 0 : elapsed * Math.PI / 2
      rosette.rotation.y = spin
      globeGrid.rotation.y = elapsed * .026
      for (const node of satellites) {
        const active = node.key === (latest.current.highlighted ?? latest.current.selected)
        node.group.position.copy(node.origin).multiplyScalar(extension)
        node.group.visible = extension > .05
        node.dot.visible = extension > .35
        node.lineMaterial.opacity = extension * (active ? 1 : .5)
        node.group.scale.setScalar(active ? 1.09 : 1)
        node.material.emissiveIntensity = active ? 0.35 : .15
        node.edgeMaterial.color.setHex(
  active ? CUBE_THEME.activeRim : CUBE_THEME.rim
)
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
      canvas.dataset.viewYaw = yaw.toFixed(4)
      canvas.dataset.animation = shouldAnimate() ? 'running' : 'resting'
      canvas.dataset.extension = extension.toFixed(4)
      canvas.dataset.spin = spin.toFixed(4)
    }
    const loop = (time: number) => {
      frame = 0
      // Cap decorative rendering at 30 fps to keep input responsive on smaller devices.
      if (time - previousTime >= 32) {
        if (shouldAnimate() && !inspecting()) elapsed += Math.min((time - previousTime) / 1000, .1)
        previousTime = time
        paint()
      }
      if (shouldAnimate()) frame = requestAnimationFrame(loop)
    }
    const sync = () => {
      if (frame) cancelAnimationFrame(frame)
      frame = 0
      previousTime = performance.now()
      paint()
      if (shouldAnimate()) frame = requestAnimationFrame(loop)
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
    const move = (event: PointerEvent) => {
      if (dragging) {
        targetYaw = Math.max(-.5, Math.min(.5, targetYaw + (event.clientX - previousX) * .0035))
        targetPitch = Math.max(-.22, Math.min(.22, targetPitch + (event.clientY - previousY) * .0025))
        previousX = event.clientX
        previousY = event.clientY
        if (!shouldAnimate()) { yaw = targetYaw; pitch = targetPitch; paint() }
      } else if (event.pointerType === 'mouse' && !latest.current.reducedMotion && !latest.current.paused) {
        const rect = interaction.getBoundingClientRect()
        targetYaw = -.06 + ((event.clientX - rect.left) / rect.width - .5) * .2
        targetPitch = .035 + ((event.clientY - rect.top) / rect.height - .5) * .08
      }
      if (!dragging && !(event.target as Element).closest('button')) latest.current.onHighlight(pick(event))
    }
    const down = (event: PointerEvent) => {
      if (event.button !== 0 || (event.target as Element).closest('button')) return
      dragging = true
      previousX = event.clientX
      previousY = event.clientY
      pressX = event.clientX
      pressY = event.clientY
      pressedNode = pick(event)
      interaction.setPointerCapture(event.pointerId)
      interaction.classList.add('is-dragging')
    }
    const up = (event: PointerEvent) => {
      if (dragging && event.type === 'pointerup' && pressedNode && Math.hypot(event.clientX - pressX, event.clientY - pressY) < 8) latest.current.onSelect(pressedNode)
      dragging = false
      pressedNode = null
      if (interaction.hasPointerCapture(event.pointerId)) interaction.releasePointerCapture(event.pointerId)
      interaction.classList.remove('is-dragging')
    }
    const leave = () => {
      if (!dragging) { targetYaw = -.06; targetPitch = .035 }
      latest.current.onHighlight(null)
    }
    const keydown = (event: KeyboardEvent) => {
      if (event.target !== interaction || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
      event.preventDefault()
      if (event.key === 'ArrowLeft') targetYaw = Math.max(-.5, targetYaw - .1)
      if (event.key === 'ArrowRight') targetYaw = Math.min(.5, targetYaw + .1)
      if (event.key === 'ArrowUp') targetPitch = Math.max(-.22, targetPitch - .06)
      if (event.key === 'ArrowDown') targetPitch = Math.min(.22, targetPitch + .06)
      if (!shouldAnimate()) { yaw = targetYaw; pitch = targetPitch; paint() }
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
