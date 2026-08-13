import { useEffect, useRef } from 'react'

type AmbientPoint = {
  x: number
  y: number
  depth: number
  phase: number
  speed: number
  radius: number
}

type SurveyBeacon = {
  x: number
  y: number
  phase: number
}

type DataArc = {
  from: readonly [number, number]
  to: readonly [number, number]
  bend: number
  speed: number
  offset: number
}

const BEACONS: SurveyBeacon[] = [
  { x: 0.11, y: 0.76, phase: 0.2 },
  { x: 0.20, y: 0.66, phase: 1.4 },
  { x: 0.31, y: 0.71, phase: 2.2 },
  { x: 0.39, y: 0.60, phase: 3.1 },
  { x: 0.47, y: 0.68, phase: 4.0 },
  { x: 0.55, y: 0.56, phase: 4.9 },
]

const DATA_ARCS: DataArc[] = [
  { from: [0.20, 0.66], to: [0.66, 0.34], bend: -0.16, speed: 0.058, offset: 0.08 },
  { from: [0.31, 0.71], to: [0.70, 0.53], bend: -0.10, speed: 0.052, offset: 0.52 },
  { from: [0.39, 0.60], to: [0.62, 0.25], bend: -0.20, speed: 0.047, offset: 0.78 },
]

function seededRandom(seed: number) {
  let state = seed >>> 0
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 4294967296
  }
}

function createAmbientPoints(width: number, height: number, count: number): AmbientPoint[] {
  const random = seededRandom(Math.max(1, Math.round(width * 0.61 + height * 0.39)))
  return Array.from({ length: count }, (_, index) => ({
    x: width * (0.018 + random() * 0.964),
    y: height * (0.08 + random() * 0.84),
    depth: 0.22 + random() * 0.78,
    phase: random() * Math.PI * 2 + index * 0.41,
    speed: 0.12 + random() * 0.32,
    radius: 0.35 + random() * 0.85,
  }))
}

function quadraticPoint(
  startX: number,
  startY: number,
  controlX: number,
  controlY: number,
  endX: number,
  endY: number,
  t: number,
) {
  const mt = 1 - t
  return {
    x: mt * mt * startX + 2 * mt * t * controlX + t * t * endX,
    y: mt * mt * startY + 2 * mt * t * controlY + t * t * endY,
  }
}

function arcGeometry(arc: DataArc, width: number, height: number) {
  const startX = arc.from[0] * width
  const startY = arc.from[1] * height
  const endX = arc.to[0] * width
  const endY = arc.to[1] * height
  const dx = endX - startX
  const dy = endY - startY
  const distance = Math.hypot(dx, dy) || 1
  return {
    startX,
    startY,
    endX,
    endY,
    controlX: (startX + endX) / 2 + (-dy / distance) * distance * arc.bend,
    controlY: (startY + endY) / 2 + (dx / distance) * distance * arc.bend,
  }
}

function terrainY(
  normalizedX: number,
  row: number,
  rowCount: number,
  seconds: number,
  width: number,
  height: number,
  pointer: { x: number; y: number; active: boolean },
) {
  const depth = rowCount <= 1 ? 0 : row / (rowCount - 1)
  const base = height * (0.57 + depth * 0.39)
  const amplitude = height * (0.012 + (1 - depth) * 0.014)
  const ridge = Math.exp(-Math.pow((normalizedX - 0.43) / 0.24, 2)) * height * (0.018 + (1 - depth) * 0.018)
  const wave =
    Math.sin(normalizedX * Math.PI * 3.15 + row * 0.47 + seconds * 0.095) * amplitude +
    Math.sin(normalizedX * Math.PI * 7.4 - row * 0.31 - seconds * 0.065) * amplitude * 0.34

  let pointerLift = 0
  if (pointer.active && pointer.x < width * 0.72) {
    const px = normalizedX * width * 0.68
    const py = base + wave - ridge
    const distance = Math.hypot(pointer.x - px, pointer.y - py)
    const radius = Math.min(230, Math.max(145, width * 0.16))
    if (distance < radius) {
      const influence = 1 - distance / radius
      pointerLift = -height * 0.022 * influence * influence
    }
  }

  return base + wave - ridge + pointerLift
}

export function LoginNetworkMotionCanvas() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || typeof window === 'undefined') return

    const context = canvas.getContext('2d')
    if (!context) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const coarsePointer = window.matchMedia('(pointer: coarse)')
    const host = canvas.parentElement
    let width = 1
    let height = 1
    let dpr = 1
    let animationFrame = 0
    let paused = document.hidden
    let ambientPoints: AmbientPoint[] = []
    const pointer = { x: -1000, y: -1000, active: false }

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      dpr = Math.min(window.devicePixelRatio || 1, 1.6)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      ambientPoints = createAmbientPoints(width, height, coarsePointer.matches ? 26 : 58)
    }

    const updatePointer = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      pointer.x = event.clientX - rect.left
      pointer.y = event.clientY - rect.top
      pointer.active = pointer.x >= 0 && pointer.y >= 0 && pointer.x <= rect.width && pointer.y <= rect.height
    }

    const clearPointer = () => {
      pointer.active = false
    }

    const drawAmbient = (seconds: number) => {
      const targetX = pointer.active ? pointer.x : width * 0.45
      const targetY = pointer.active ? pointer.y : height * 0.48
      const nx = (targetX / Math.max(1, width) - 0.5) * 2
      const ny = (targetY / Math.max(1, height) - 0.5) * 2

      context.save()
      context.globalCompositeOperation = 'lighter'
      for (const point of ambientPoints) {
        const driftX = Math.sin(seconds * point.speed + point.phase) * (1.5 + point.depth * 3.2)
        const driftY = Math.cos(seconds * point.speed * 0.74 + point.phase) * (1.1 + point.depth * 2.2)
        const x = point.x + driftX + nx * point.depth * 3.6
        const y = point.y + driftY + ny * point.depth * 2.6
        const shimmer = 0.08 + (Math.sin(seconds * 0.55 + point.phase) + 1) * 0.045
        context.fillStyle = `rgba(93, 203, 235, ${shimmer * (0.55 + point.depth * 0.45)})`
        context.beginPath()
        context.arc(x, y, point.radius, 0, Math.PI * 2)
        context.fill()
      }
      context.restore()
    }

    const drawTerrain = (seconds: number) => {
      const mobile = width < 760
      const rowCount = mobile ? 9 : 14
      const samples = mobile ? 32 : 52
      const maxX = mobile ? 1 : 0.68

      context.save()
      context.lineCap = 'round'
      context.lineJoin = 'round'

      for (let row = 0; row < rowCount; row += 1) {
        const depth = rowCount <= 1 ? 0 : row / (rowCount - 1)
        const alpha = (0.055 + (1 - depth) * 0.075) * (mobile ? 0.72 : 1)
        const lineWidth = 0.45 + (1 - depth) * 0.34
        const gradient = context.createLinearGradient(0, 0, width * maxX, 0)
        gradient.addColorStop(0, `rgba(26, 157, 196, ${alpha * 0.38})`)
        gradient.addColorStop(0.35, `rgba(47, 205, 226, ${alpha})`)
        gradient.addColorStop(0.76, `rgba(23, 126, 221, ${alpha * 0.72})`)
        gradient.addColorStop(1, 'rgba(24, 91, 204, 0)')

        context.beginPath()
        for (let sample = 0; sample <= samples; sample += 1) {
          const normalizedX = sample / samples
          const x = normalizedX * width * maxX
          const y = terrainY(normalizedX, row, rowCount, seconds, width, height, pointer)
          if (sample === 0) context.moveTo(x, y)
          else context.lineTo(x, y)
        }
        context.strokeStyle = gradient
        context.lineWidth = lineWidth
        context.stroke()
      }

      context.restore()
    }

    const drawBeacons = (seconds: number) => {
      context.save()
      context.globalCompositeOperation = 'lighter'
      for (const beacon of BEACONS) {
        const x = beacon.x * width
        const y = beacon.y * height
        const pointerDistance = pointer.active ? Math.hypot(pointer.x - x, pointer.y - y) : 9999
        const proximity = pointerDistance < 180 ? 1 - pointerDistance / 180 : 0
        const pulse = 0.5 + 0.5 * Math.sin(seconds * 1.05 + beacon.phase)
        const glowRadius = 7 + proximity * 5 + pulse * 2
        const glow = context.createRadialGradient(x, y, 0, x, y, glowRadius)
        glow.addColorStop(0, `rgba(230, 253, 255, ${0.58 + proximity * 0.26})`)
        glow.addColorStop(0.24, `rgba(56, 214, 235, ${0.30 + proximity * 0.18})`)
        glow.addColorStop(1, 'rgba(11, 103, 215, 0)')
        context.fillStyle = glow
        context.beginPath()
        context.arc(x, y, glowRadius, 0, Math.PI * 2)
        context.fill()

        context.fillStyle = `rgba(206, 250, 255, ${0.48 + proximity * 0.38})`
        context.beginPath()
        context.arc(x, y, 1.05 + proximity * 0.65, 0, Math.PI * 2)
        context.fill()

        context.strokeStyle = `rgba(42, 194, 226, ${0.055 + pulse * 0.045 + proximity * 0.08})`
        context.lineWidth = 0.7
        context.beginPath()
        context.arc(x, y, 5.5 + pulse * 3.5, 0, Math.PI * 2)
        context.stroke()
      }
      context.restore()
    }

    const drawDataArcs = (seconds: number, animate: boolean) => {
      context.save()
      context.globalCompositeOperation = 'lighter'
      context.lineCap = 'round'

      for (const arc of DATA_ARCS) {
        const geometry = arcGeometry(arc, width, height)
        const midpoint = quadraticPoint(
          geometry.startX,
          geometry.startY,
          geometry.controlX,
          geometry.controlY,
          geometry.endX,
          geometry.endY,
          0.5,
        )
        const pointerDistance = pointer.active ? Math.hypot(pointer.x - midpoint.x, pointer.y - midpoint.y) : 9999
        const proximity = pointerDistance < 230 ? 1 - pointerDistance / 230 : 0

        const pathGradient = context.createLinearGradient(geometry.startX, geometry.startY, geometry.endX, geometry.endY)
        pathGradient.addColorStop(0, `rgba(24, 160, 200, ${0.06 + proximity * 0.035})`)
        pathGradient.addColorStop(0.58, `rgba(43, 185, 226, ${0.10 + proximity * 0.05})`)
        pathGradient.addColorStop(1, 'rgba(22, 101, 219, 0)')
        context.strokeStyle = pathGradient
        context.lineWidth = 0.8 + proximity * 0.35
        context.beginPath()
        context.moveTo(geometry.startX, geometry.startY)
        context.quadraticCurveTo(geometry.controlX, geometry.controlY, geometry.endX, geometry.endY)
        context.stroke()

        if (!animate) continue

        const t = (seconds * arc.speed + arc.offset) % 1
        const head = quadraticPoint(
          geometry.startX,
          geometry.startY,
          geometry.controlX,
          geometry.controlY,
          geometry.endX,
          geometry.endY,
          t,
        )
        const tail = quadraticPoint(
          geometry.startX,
          geometry.startY,
          geometry.controlX,
          geometry.controlY,
          geometry.endX,
          geometry.endY,
          Math.max(0, t - 0.085),
        )
        const pulse = context.createLinearGradient(tail.x, tail.y, head.x, head.y)
        pulse.addColorStop(0, 'rgba(20, 119, 218, 0)')
        pulse.addColorStop(0.62, 'rgba(54, 205, 235, 0.50)')
        pulse.addColorStop(1, 'rgba(228, 253, 255, 0.90)')
        context.strokeStyle = pulse
        context.lineWidth = 1.25
        context.beginPath()
        context.moveTo(tail.x, tail.y)
        context.lineTo(head.x, head.y)
        context.stroke()

        const glow = context.createRadialGradient(head.x, head.y, 0, head.x, head.y, 7)
        glow.addColorStop(0, 'rgba(244, 255, 255, 0.84)')
        glow.addColorStop(0.30, 'rgba(72, 218, 242, 0.50)')
        glow.addColorStop(1, 'rgba(13, 93, 220, 0)')
        context.fillStyle = glow
        context.beginPath()
        context.arc(head.x, head.y, 7, 0, Math.PI * 2)
        context.fill()
      }

      context.restore()
    }

    const drawAmbientRibbon = (seconds: number) => {
      if (width < 680) return

      const left = width * 0.035
      const right = width * 0.62
      const y = height * 0.31
      const shift = Math.sin(seconds * 0.12) * height * 0.012
      const gradient = context.createLinearGradient(left, y, right, y)
      gradient.addColorStop(0, 'rgba(15, 154, 193, 0)')
      gradient.addColorStop(0.34, 'rgba(38, 196, 221, 0.065)')
      gradient.addColorStop(0.72, 'rgba(30, 129, 225, 0.045)')
      gradient.addColorStop(1, 'rgba(27, 82, 203, 0)')

      context.save()
      context.strokeStyle = gradient
      context.lineWidth = 1
      context.beginPath()
      context.moveTo(left, y + shift)
      context.bezierCurveTo(width * 0.19, height * 0.24, width * 0.40, height * 0.40, right, height * 0.29 + shift)
      context.stroke()
      context.restore()
    }

    const render = (seconds: number, animate: boolean) => {
      context.clearRect(0, 0, width, height)
      drawAmbient(seconds)
      drawAmbientRibbon(seconds)
      drawTerrain(seconds)
      drawDataArcs(seconds, animate)
      drawBeacons(seconds)
    }

    const drawFrame = (now: number) => {
      if (paused) return
      render(now / 1000, true)
      animationFrame = window.requestAnimationFrame(drawFrame)
    }

    const renderStatic = () => {
      render(0, false)
    }

    const handleVisibilityChange = () => {
      paused = document.hidden
      if (paused) {
        if (animationFrame) window.cancelAnimationFrame(animationFrame)
        animationFrame = 0
        return
      }
      if (!reducedMotion.matches && !animationFrame) {
        animationFrame = window.requestAnimationFrame(drawFrame)
      }
    }

    const resizeObserver = typeof ResizeObserver !== 'undefined' && host
      ? new ResizeObserver(() => resize())
      : null

    resize()
    if (resizeObserver && host) resizeObserver.observe(host)
    window.addEventListener('resize', resize)
    window.addEventListener('pointermove', updatePointer, { passive: true })
    window.addEventListener('pointerleave', clearPointer)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    if (reducedMotion.matches) renderStatic()
    else if (!paused) animationFrame = window.requestAnimationFrame(drawFrame)

    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      resizeObserver?.disconnect()
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', updatePointer)
      window.removeEventListener('pointerleave', clearPointer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  return <canvas ref={canvasRef} className="login-network-motion-canvas" aria-hidden="true" />
}
