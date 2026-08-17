import { useEffect, useRef } from 'react'
import '../login-particle-field.css'

type ParticleDepth = 0 | 1 | 2

type Particle = {
  x: number
  y: number
  vx: number
  vy: number
  depth: ParticleDepth
  radius: number
  alpha: number
  phase: number
  twinkle: number
  previousX: number
  previousY: number
}

type AvoidRect = {
  left: number
  top: number
  right: number
  bottom: number
}

const DEPTH_PARALLAX = [5, 10, 17] as const
const DEPTH_SPEED = [0.10, 0.18, 0.28] as const
const DEPTH_ALPHA = [0.28, 0.48, 0.78] as const
const DEPTH_RADIUS = [0.55, 0.85, 1.20] as const

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function particleCount(width: number, height: number, compact: boolean) {
  const density = compact ? 15000 : 9000
  return clamp(Math.round((width * height) / density), compact ? 72 : 118, compact ? 150 : 260)
}

function createParticle(width: number, height: number, index: number): Particle {
  const depth = (index % 3) as ParticleDepth
  const speed = DEPTH_SPEED[depth]
  const angle = Math.random() * Math.PI * 2
  const speedVariance = 0.48 + Math.random() * 0.86
  const radiusVariance = 0.72 + Math.random() * 0.62

  return {
    x: Math.random() * width,
    y: Math.random() * height,
    vx: Math.cos(angle) * speed * speedVariance,
    vy: Math.sin(angle) * speed * speedVariance,
    depth,
    radius: DEPTH_RADIUS[depth] * radiusVariance,
    alpha: DEPTH_ALPHA[depth] * (0.68 + Math.random() * 0.32),
    phase: Math.random() * Math.PI * 2,
    twinkle: 0.00055 + Math.random() * 0.0011,
    previousX: Number.NaN,
    previousY: Number.NaN,
  }
}

function distanceFromRect(x: number, y: number, rect: AvoidRect) {
  const dx = Math.max(rect.left - x, 0, x - rect.right)
  const dy = Math.max(rect.top - y, 0, y - rect.bottom)
  return Math.hypot(dx, dy)
}

export function LoginParticleField() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || typeof window === 'undefined') return

    const context = canvas.getContext('2d', { alpha: true })
    if (!context) return

    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const coarsePointerQuery = window.matchMedia('(pointer: coarse)')

    let width = 1
    let height = 1
    let dpr = 1
    let particles: Particle[] = []
    let animationFrame = 0
    let lastFrameTime = performance.now()
    let frameNumber = 0
    let reducedMotion = reducedMotionQuery.matches
    let compact = coarsePointerQuery.matches
    let canvasRect = canvas.getBoundingClientRect()
    let avoidRect: AvoidRect | null = null

    const pointer = {
      x: width * 0.42,
      y: height * 0.5,
      targetX: width * 0.42,
      targetY: height * 0.5,
      active: false,
    }

    const measureAvoidRect = () => {
      const panel = document.querySelector<HTMLElement>('.final-login-panel')
      canvasRect = canvas.getBoundingClientRect()
      if (!panel) {
        avoidRect = null
        return
      }

      const rect = panel.getBoundingClientRect()
      const padding = compact ? 18 : 46
      avoidRect = {
        left: rect.left - canvasRect.left - padding,
        top: rect.top - canvasRect.top - padding,
        right: rect.right - canvasRect.left + padding,
        bottom: rect.bottom - canvasRect.top + padding,
      }
    }

    const resize = () => {
      canvasRect = canvas.getBoundingClientRect()
      width = Math.max(1, Math.round(canvasRect.width))
      height = Math.max(1, Math.round(canvasRect.height))
      compact = coarsePointerQuery.matches || width < 860
      dpr = Math.min(window.devicePixelRatio || 1, compact ? 1.2 : 1.6)

      canvas.width = Math.max(1, Math.round(width * dpr))
      canvas.height = Math.max(1, Math.round(height * dpr))
      context.setTransform(dpr, 0, 0, dpr, 0, 0)

      const count = particleCount(width, height, compact)
      particles = Array.from({ length: count }, (_, index) => createParticle(width, height, index))

      pointer.x = width * 0.42
      pointer.y = height * 0.5
      pointer.targetX = pointer.x
      pointer.targetY = pointer.y
      measureAvoidRect()
    }

    const onPointerMove = (event: PointerEvent) => {
      if (reducedMotion || coarsePointerQuery.matches) return
      canvasRect = canvas.getBoundingClientRect()
      pointer.targetX = clamp(event.clientX - canvasRect.left, 0, width)
      pointer.targetY = clamp(event.clientY - canvasRect.top, 0, height)
      pointer.active = true
    }

    const onPointerLeave = () => {
      pointer.active = false
      pointer.targetX = width * 0.42
      pointer.targetY = height * 0.5
    }

    const onVisibilityChange = () => {
      if (document.hidden && animationFrame) {
        window.cancelAnimationFrame(animationFrame)
        animationFrame = 0
      } else if (!document.hidden && !animationFrame && !reducedMotion) {
        lastFrameTime = performance.now()
        animationFrame = window.requestAnimationFrame(drawFrame)
      }
    }

    const drawFrame = (time: number) => {
      animationFrame = 0
      const delta = clamp((time - lastFrameTime) / 16.667, 0.35, 2.2)
      lastFrameTime = time
      frameNumber += 1

      if (frameNumber % 12 === 0) measureAvoidRect()

      pointer.x += (pointer.targetX - pointer.x) * 0.075
      pointer.y += (pointer.targetY - pointer.y) * 0.075

      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      context.clearRect(0, 0, width, height)
      context.globalCompositeOperation = 'lighter'
      context.lineCap = 'round'

      const normalizedPointerX = width ? (pointer.x / width) * 2 - 1 : 0
      const normalizedPointerY = height ? (pointer.y / height) * 2 - 1 : 0

      for (const particle of particles) {
        const depth = particle.depth
        if (!reducedMotion) {
          particle.x += particle.vx * delta
          particle.y += particle.vy * delta
        }

        if (particle.x < -16) particle.x = width + 16
        if (particle.x > width + 16) particle.x = -16
        if (particle.y < -16) particle.y = height + 16
        if (particle.y > height + 16) particle.y = -16

        const parallax = pointer.active ? DEPTH_PARALLAX[depth] : DEPTH_PARALLAX[depth] * 0.18
        let screenX = particle.x - normalizedPointerX * parallax
        let screenY = particle.y - normalizedPointerY * parallax * 0.72

        if (pointer.active && !reducedMotion) {
          const dx = screenX - pointer.x
          const dy = screenY - pointer.y
          const distance = Math.hypot(dx, dy)
          const influenceRadius = 92 + depth * 34
          if (distance > 0.01 && distance < influenceRadius) {
            const influence = 1 - distance / influenceRadius
            const displacement = influence * influence * (5 + depth * 5.5)
            screenX += (dx / distance) * displacement
            screenY += (dy / distance) * displacement
          }
        }

        const twinkle = reducedMotion ? 0.9 : 0.78 + Math.sin(time * particle.twinkle + particle.phase) * 0.22
        let alpha = particle.alpha * twinkle

        if (avoidRect) {
          const distanceToPanel = distanceFromRect(screenX, screenY, avoidRect)
          if (distanceToPanel === 0) alpha *= 0.08
          else if (distanceToPanel < 88) alpha *= 0.18 + (distanceToPanel / 88) * 0.58
        }

        if (Number.isFinite(particle.previousX) && Number.isFinite(particle.previousY) && !reducedMotion) {
          const trailAlpha = alpha * (0.045 + depth * 0.018)
          context.beginPath()
          context.moveTo(particle.previousX, particle.previousY)
          context.lineTo(screenX, screenY)
          context.strokeStyle = `rgba(73, 218, 242, ${trailAlpha})`
          context.lineWidth = 0.45 + depth * 0.12
          context.stroke()
        }

        const glowRadius = particle.radius * (2.7 + depth * 0.5)
        context.beginPath()
        context.arc(screenX, screenY, glowRadius, 0, Math.PI * 2)
        context.fillStyle = `rgba(38, 180, 224, ${alpha * 0.06})`
        context.fill()

        context.beginPath()
        context.arc(screenX, screenY, particle.radius, 0, Math.PI * 2)
        context.fillStyle = depth === 2
          ? `rgba(217, 251, 255, ${alpha})`
          : `rgba(94, 220, 244, ${alpha})`
        context.fill()

        particle.previousX = screenX
        particle.previousY = screenY
      }

      context.globalCompositeOperation = 'source-over'
      if (!reducedMotion && !document.hidden) {
        animationFrame = window.requestAnimationFrame(drawFrame)
      }
    }

    const syncMotionPreference = () => {
      reducedMotion = reducedMotionQuery.matches
      if (animationFrame) {
        window.cancelAnimationFrame(animationFrame)
        animationFrame = 0
      }
      lastFrameTime = performance.now()
      if (reducedMotion) drawFrame(lastFrameTime)
      else animationFrame = window.requestAnimationFrame(drawFrame)
    }

    resize()
    window.addEventListener('resize', resize, { passive: true })
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', onPointerLeave)
    document.addEventListener('visibilitychange', onVisibilityChange)
    reducedMotionQuery.addEventListener?.('change', syncMotionPreference)
    coarsePointerQuery.addEventListener?.('change', resize)

    if (reducedMotion) drawFrame(performance.now())
    else animationFrame = window.requestAnimationFrame(drawFrame)

    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', onPointerMove)
      document.documentElement.removeEventListener('pointerleave', onPointerLeave)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      reducedMotionQuery.removeEventListener?.('change', syncMotionPreference)
      coarsePointerQuery.removeEventListener?.('change', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="naksha-login-particle-field" aria-hidden="true" />
}
