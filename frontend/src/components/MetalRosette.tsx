import { useEffect, useRef, type CSSProperties } from 'react'

/*
 * MetalRosette — canvas renderer for the NakshaTech welcome hero.
 *
 * Motion is synchronised with the CSS department labels:
 *   the hero sets `--rosette-cycle` from ROSETTE_CYCLE_SECONDS and passes
 *   the same value here as `cycleSeconds`. Both timelines run the identical
 *   cycle — closed 0–19%, expand 19–36%, hold 36–82%, collapse 82–100% —
 *   matching the `rosette-department-cycle` keyframes exactly, so labels
 *   never appear before a cube arrives or linger after it collapses.
 *
 * Reduced motion: when the user prefers reduced motion the canvas paints a
 *   single static, fully-expanded frame and the requestAnimationFrame loop
 *   is never started (and cancelled if the preference flips live).
 *
 * Department labels: `onCubeLayout` reports the projected cube centres in
 *   percent of the canvas box so the hero can place labels ON the cubes
 *   instead of at hand-tuned percentages.
 */

export interface MetalRosetteMaterial {
  roughness?: number
  reflect?: number
}

export interface MetalRosetteMotion {
  spin?: number
  travel?: number
  hold?: number
}

export interface MetalRosetteCamera {
  tilt?: number
  sideTilt?: number
}

export interface MetalRosetteProps {
  background?: string
  baseColor?: string
  speed?: number
  distance?: number
  material?: MetalRosetteMaterial
  motion?: MetalRosetteMotion
  camera?: MetalRosetteCamera
  style?: CSSProperties
  /** Seconds per expand/hold/collapse cycle — must match `--rosette-cycle`. */
  cycleSeconds?: number
  /** Projected cube centres (percent of canvas box), reported per layout. */
  onCubeLayout?: (positions: Record<string, { x: number; y: number }>) => void
  /**
   * Per-frame sync — fired every animation frame (and once for the static
   * reduced-motion frame) with the EXACT extension value driving cube travel,
   * plus the live interpolated cube centres. Consumers must move labels with
   * this value (never a parallel CSS/JS clock) so no frame ever shows a cube
   * that has moved while its label stayed behind.
   */
  onRosetteFrame?: (frame: RosetteFrame) => void
}

/** One projected cube centre, percent of the canvas box. */
export interface RosetteCubeCenter {
  x: number
  y: number
}

/** Single animation frame of the expand/hold/collapse cycle. */
export interface RosetteFrame {
  /** Expand/collapse extension — the exact value driving cube travel. */
  extension: number
  /** Live cube centres: closed (50/50) + (open − closed) × extension. */
  centers: Record<string, RosetteCubeCenter>
}

interface CubePlacement {
  key: string
  x: number
  y: number
  depth: number
}

/* Fixed rosette geometry — angles are degrees on a unit circle in the
   vertical plane (y up). The camera yaws the plane by `camera.tilt`
   (default 35°). Ring radius is RING_SCALE of the canvas so the expanded
   object stays compact: x = 50% ± 24%, y = 16%–84%. */
const DEPARTMENTS: { key: string; angle: number }[] = [
  { key: 'gis', angle: 90 },
  { key: 'lidar', angle: 150 },
  { key: 'ortho', angle: 30 },
  { key: 'civil', angle: 210 },
  { key: 'drone', angle: 330 },
  { key: 'survey', angle: 270 },
]

/* Ring radius as a fraction of the square canvas (34% → labels 16%–84%).
   Single source of truth: WebGL cube travel, the static layout report,
   the per-frame label sync and the CSS fallbacks all derive from this. */
const RING_SCALE = 0.34
/** Department cube half-width as a fraction of the canvas. */
const CUBE_SCALE = 0.114
/** Central hub cube half-width as a fraction of the canvas. */
const HUB_SCALE = 0.158
type Face = [number, number][]

function facePath(ctx: CanvasRenderingContext2D, cx: number, cy: number, face: Face): void {
  ctx.beginPath()
  face.forEach(([fx, fy], index) => {
    const px = cx + fx
    const py = cy + fy
    if (index === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  })
  ctx.closePath()
}

/**
 * Draws one isometric metal cube centred at (cx, cy).
 * `sweep` rotates the specular glint using the `speed` prop so the light
 * feels alive without rotating the object itself (motion.spin stays 0).
 */
function drawCube(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  half: number,
  rgb: [number, number, number],
  reflect: number,
  roughness: number,
  alpha: number,
  sweep: number,
): void {
  if (alpha <= 0.015 || half <= 0.5) return

  const gloss = Math.min(1, Math.max(0, reflect / 100))
  const top: Face = [
    [0, -half],
    [half, -half * 0.5],
    [0, 0],
    [-half, -half * 0.5],
  ]
  const left: Face = [
    [-half, -half * 0.5],
    [0, 0],
    [0, half],
    [-half, half * 0.5],
  ]
  const right: Face = [
    [half, -half * 0.5],
    [0, 0],
    [0, half],
    [half, half * 0.5],
  ]

  ctx.save()
  ctx.globalAlpha = alpha

  facePath(ctx, cx, cy, right)
  ctx.fillStyle = shade(rgb, -0.44 + 0.1 * gloss)
  ctx.fill()

  facePath(ctx, cx, cy, left)
  ctx.fillStyle = shade(rgb, -0.2 + 0.06 * gloss)
  ctx.fill()

  facePath(ctx, cx, cy, top)
  ctx.fillStyle = shade(rgb, 0.26 + 0.3 * gloss)
  ctx.fill()

  /* Specular glint on the top face — tighter when roughness is low. */
  const glintX = cx - half * 0.2 + Math.cos(sweep) * half * 0.28
  const glintY = cy - half * 0.62 + Math.sin(sweep) * half * 0.18
  const tightness = 1 - Math.min(1, Math.max(0, roughness / 100))
  const glow = ctx.createRadialGradient(glintX, glintY, 0, glintX, glintY, half * 1.1)
  glow.addColorStop(0, `rgba(255, 255, 255, ${0.16 + 0.34 * gloss * (0.4 + 0.6 * tightness)})`)
  glow.addColorStop(1, 'rgba(255, 255, 255, 0)')
  facePath(ctx, cx, cy, top)
  ctx.fillStyle = glow
  ctx.fill()

  /* Edge highlights. */
  ctx.lineWidth = Math.max(1, half * 0.05)
  ctx.strokeStyle = `rgba(238, 252, 255, ${0.2 + 0.28 * gloss})`
  facePath(ctx, cx, cy, top)
  ctx.stroke()
  facePath(ctx, cx, cy, left)
  ctx.stroke()
  facePath(ctx, cx, cy, right)
  ctx.stroke()

  /* NakshaTech cyan rim along the base. */
  ctx.lineWidth = Math.max(1, half * 0.06)
  ctx.strokeStyle = 'rgba(64, 214, 255, 0.3)'
  ctx.beginPath()
  ctx.moveTo(cx - half, cy + half * 0.5)
  ctx.lineTo(cx, cy + half)
  ctx.lineTo(cx + half, cy + half * 0.5)
  ctx.stroke()

  ctx.restore()
}


function hexToRgb(hex: string): [number, number, number] {
  const value = hex.replace('#', '')
  const full = value.length === 3
    ? value.split('').map(char => char + char).join('')
    : value
  const parsed = Number.parseInt(full.slice(0, 6), 16)
  if (Number.isNaN(parsed)) return [159, 179, 200]
  return [(parsed >> 16) & 255, (parsed >> 8) & 255, parsed & 255]
}

function shade(rgb: [number, number, number], amount: number): string {
  const mix = (channel: number) => {
    const target = amount >= 0 ? 255 : 0
    return Math.round(channel + (target - channel) * Math.abs(amount))
  }
  return `rgb(${mix(rgb[0])}, ${mix(rgb[1])}, ${mix(rgb[2])})`
}

/** Expand/collapse progress — mirrors `rosette-department-cycle` exactly. */
function cycleProgress(t: number): number {
  if (t < 0.19) return 0
  if (t < 0.36) return (t - 0.19) / 0.17
  if (t < 0.82) return 1
  return 1 - (t - 0.82) / 0.18
}


/** Live cube centres (% of canvas box) for an extension value — the single
 * formula behind WebGL travel, the layout report and the per-frame sync:
 * centre = closed (50/50) + (open − closed) × progress. */
function projectCenters(progress: number, yaw: number): Record<string, RosetteCubeCenter> {
  const centers: Record<string, RosetteCubeCenter> = {}
  for (const { key, angle } of DEPARTMENTS) {
    const radian = (angle * Math.PI) / 180
    centers[key] = {
      x: (0.5 + RING_SCALE * Math.cos(radian) * Math.cos(yaw) * progress) * 100,
      y: (0.5 - RING_SCALE * Math.sin(radian) * progress) * 100,
    }
  }
  return centers
}


/** Renders one frame: hub, spokes and the six department cubes. */
function renderScene(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  progress: number,
  sweep: number,
  rgb: [number, number, number],
  reflect: number,
  roughness: number,
  yaw: number,
): void {
  const size = Math.min(width, height)
  const cx = width / 2
  const cy = height / 2
  const ring = RING_SCALE * size
  const cubeHalf = CUBE_SCALE * size

  ctx.clearRect(0, 0, width, height)

  const placements: CubePlacement[] = DEPARTMENTS.map(({ key, angle }) => {
    const radian = (angle * Math.PI) / 180
    const worldX = Math.cos(radian)
    const worldY = Math.sin(radian)
    const targetX = cx + worldX * Math.cos(yaw) * ring
    const targetY = cy - worldY * ring
    return {
      key,
      x: cx + (targetX - cx) * progress,
      y: cy + (targetY - cy) * progress,
      depth: -worldX * Math.sin(yaw),
    }
  })

  /* Light spokes from the hub toward each cube while the rosette opens. */
  if (progress > 0.01) {
    ctx.save()
    ctx.lineWidth = Math.max(1, size * 0.004)
    for (const placement of placements) {
      const gradient = ctx.createLinearGradient(cx, cy, placement.x, placement.y)
      gradient.addColorStop(0, 'rgba(64, 214, 255, 0)')
      gradient.addColorStop(1, `rgba(64, 214, 255, ${0.22 * progress})`)
      ctx.strokeStyle = gradient
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(placement.x, placement.y)
      ctx.stroke()
    }
    ctx.restore()
  }

  /* Central hub — always present; the CSS core logo sits on its face. */
  drawCube(ctx, cx, cy, HUB_SCALE * size, rgb, reflect, roughness, 1, sweep)

  /* Department cubes — painter sorted so nearer cubes draw last. */
  const ordered = [...placements].sort((a, b) => a.depth - b.depth)
  for (const placement of ordered) {
    drawCube(ctx, placement.x, placement.y, cubeHalf, rgb, reflect, roughness, progress, sweep)
  }
}


export default function MetalRosette({
  background = 'transparent',
  baseColor = '#9fb3c8',
  speed,
  material,
  camera,
  style,
  cycleSeconds = 6.16,
  onCubeLayout,
  onRosetteFrame,
}: MetalRosetteProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  /* Projected cube centres (percent of the canvas box) — deterministic for
     the fixed camera, reported so hero labels stay attached to the cubes. */
  useEffect(() => {
    if (!onCubeLayout) return
    const yaw = ((camera?.tilt ?? 35) * Math.PI) / 180
    const positions: Record<string, { x: number; y: number }> = {}
    for (const { key, angle } of DEPARTMENTS) {
      const radian = (angle * Math.PI) / 180
      positions[key] = {
        x: 50 + RING_SCALE * 100 * Math.cos(radian) * Math.cos(yaw),
        y: 50 - RING_SCALE * 100 * Math.sin(radian),
      }
    }
    onCubeLayout(positions)
  }, [camera?.tilt, onCubeLayout])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const host = canvas.parentElement
    if (!host) return

    const rgb = hexToRgb(baseColor)
    const reflect = material?.reflect ?? 90
    const roughness = material?.roughness ?? 20
    const yaw = ((camera?.tilt ?? 35) * Math.PI) / 180
    const sweepSpeed = ((speed ?? 28) / 100) * 0.1
    const cycle = Math.max(1, cycleSeconds)
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const startedAt = performance.now()

    let width = 1
    let height = 1
    let dpr = 1
    let frame = 0

    const resize = () => {
      const rect = host.getBoundingClientRect()
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = Math.max(1, Math.round(rect.width))
      height = Math.max(1, Math.round(rect.height))
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
    }

    const paint = (progress: number, sweep: number) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      renderScene(ctx, width, height, progress, sweep, rgb, reflect, roughness, yaw)
    }

    /* Push the exact extension + live centres every frame so department
       labels ride their cubes with zero drift (same value, same clock). */
    const reportFrame = (progress: number) => {
      if (onRosetteFrame) {
        onRosetteFrame({ extension: progress, centers: projectCenters(progress, yaw) })
      }
    }

    /* Reduced motion: one static, fully-expanded frame — no rAF loop. */
    const paintStatic = () => {
      paint(1, 0)
      reportFrame(1)
    }

    const loop = (now: number) => {
      const elapsed = (now - startedAt) / 1000
      const phase = (((elapsed / cycle) % 1) + 1) % 1
      const progress = cycleProgress(phase)
      paint(progress, elapsed * sweepSpeed * Math.PI * 2)
      reportFrame(progress)
      frame = window.requestAnimationFrame(loop)
    }

    const syncMotion = () => {
      if (reducedMotion.matches) {
        if (frame) {
          window.cancelAnimationFrame(frame)
          frame = 0
        }
        paintStatic()
      } else if (!frame) {
        frame = window.requestAnimationFrame(loop)
      }
    }

    const observer = new ResizeObserver(() => {
      resize()
      if (!frame) paintStatic()
    })

    resize()
    observer.observe(host)
    reducedMotion.addEventListener('change', syncMotion)
    syncMotion()

    return () => {
      observer.disconnect()
      reducedMotion.removeEventListener('change', syncMotion)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [baseColor, camera?.tilt, cycleSeconds, material?.reflect, material?.roughness, onRosetteFrame, speed])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{ background, ...style }}
    />
  )
}
