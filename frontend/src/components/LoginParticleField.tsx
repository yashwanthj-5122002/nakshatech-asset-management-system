import { useEffect, useRef } from 'react'
import '../login-particle-field.css'

type ParticleDepth = 0 | 1 | 2
type ParticleTone = 0 | 1 | 2

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
  glow: number
  tone: ParticleTone
  previousX: number
  previousY: number
}

type AvoidRect = {
  left: number
  top: number
  right: number
  bottom: number
}

type StarCluster = {
  x: number
  y: number
  spreadX: number
  spreadY: number
}

const DEPTH_PARALLAX = [11, 23, 42] as const
const DEPTH_SPEED = [0.10, 0.18, 0.29] as const
const DEPTH_ALPHA = [0.30, 0.53, 0.86] as const
const DEPTH_RADIUS = [0.48, 0.82, 1.22] as const

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function wrap(value: number, max: number) {
  if (max <= 0) return 0
  return ((value % max) + max) % max
}

function particleCount(width: number, height: number, compact: boolean) {
  const density = compact ? 7200 : 2700
  return clamp(Math.round((width * height) / density), compact ? 120 : 360, compact ? 270 : 820)
}

function chooseDepth(): ParticleDepth {
  const roll = Math.random()
  if (roll < 0.62) return 0
  if (roll < 0.90) return 1
  return 2
}

function chooseTone(): ParticleTone {
  const roll = Math.random()
  if (roll < 0.68) return 0
  if (roll < 0.91) return 1
  return 2
}

function clusteredPosition(
  width: number,
  height: number,
  clusters: StarCluster[],
) {
  if (!clusters.length || Math.random() > 0.30) {
    return {
      x: Math.random() * width,
      y: Math.random() * height,
    }
  }

  const cluster = clusters[Math.floor(Math.random() * clusters.length)]
  const gaussianX = (Math.random() + Math.random() + Math.random() + Math.random() - 2) / 2
  const gaussianY = (Math.random() + Math.random() + Math.random() + Math.random() - 2) / 2

  return {
    x: wrap(cluster.x + gaussianX * cluster.spreadX, width),
    y: wrap(cluster.y + gaussianY * cluster.spreadY, height),
  }
}

function createParticle(
  width: number,
  height: number,
  clusters: StarCluster[],
): Particle {
  const depth = chooseDepth()
  const speed = DEPTH_SPEED[depth]
  const angle = Math.random() * Math.PI * 2
  const speedVariance = 0.42 + Math.random() * 0.90
  const radiusVariance = depth === 0
    ? 0.62 + Math.random() * 0.74
    : 0.70 + Math.random() * 0.66
  const position = clusteredPosition(width, height, clusters)
  const brightStar = depth > 0 && Math.random() < 0.045

  return {
    x: position.x,
    y: position.y,
    vx: Math.cos(angle) * speed * speedVariance,
    vy: Math.sin(angle) * speed * speedVariance,
    depth,
    radius: DEPTH_RADIUS[depth] * radiusVariance * (brightStar ? 1.22 : 1),
    alpha: Math.min(0.98, DEPTH_ALPHA[depth] * (0.56 + Math.random() * 0.44) * (brightStar ? 1.16 : 1)),
    phase: Math.random() * Math.PI * 2,
    twinkle: 0.00038 + Math.random() * 0.00105,
    glow: brightStar ? 1.25 + Math.random() * 0.35 : 0.68 + Math.random() * 0.32,
    tone: chooseTone(),
    previousX: Number.NaN,
    previousY: Number.NaN,
  }
}

function createParticles(width: number, height: number, compact: boolean) {
  const count = particleCount(width, height, compact)
  const clusterCount = compact ? 3 : 6
  const clusters: StarCluster[] = Array.from({ length: clusterCount }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    spreadX: width * (0.09 + Math.random() * 0.11),
    spreadY: height * (0.08 + Math.random() * 0.12),
  }))

  return Array.from({ length: count }, () => createParticle(width, height, clusters))
}

function distanceFromRect(x: number, y: number, rect: AvoidRect) {
  const dx = Math.max(rect.left - x, 0, x - rect.right)
  const dy = Math.max(rect.top - y, 0, y - rect.bottom)
  return Math.hypot(dx, dy)
}

function starColor(tone: ParticleTone, alpha: number) {
  if (tone === 1) return `rgba(232, 249, 255, ${alpha})`
  if (tone === 2) return `rgba(203, 230, 255, ${alpha})`
  return `rgba(112, 226, 247, ${alpha})`
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
      velocityX: 0,
      velocityY: 0,
      lastTargetX: width * 0.42,
      lastTargetY: height * 0.5,
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

      particles = createParticles(width, height, compact)

      pointer.x = width * 0.42
      pointer.y = height * 0.5
      pointer.targetX = pointer.x
      pointer.targetY = pointer.y
      pointer.lastTargetX = pointer.x
      pointer.lastTargetY = pointer.y
      pointer.velocityX = 0
      pointer.velocityY = 0
      measureAvoidRect()
    }

    const onPointerMove = (event: PointerEvent) => {
      if (reducedMotion || coarsePointerQuery.matches) return
      canvasRect = canvas.getBoundingClientRect()
      const nextX = clamp(event.clientX - canvasRect.left, 0, width)
      const nextY = clamp(event.clientY - canvasRect.top, 0, height)

      pointer.velocityX = pointer.velocityX * 0.55 + (nextX - pointer.lastTargetX) * 0.45
      pointer.velocityY = pointer.velocityY * 0.55 + (nextY - pointer.lastTargetY) * 0.45
      pointer.lastTargetX = nextX
      pointer.lastTargetY = nextY
      pointer.targetX = nextX
      pointer.targetY = nextY
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

      pointer.x += (pointer.targetX - pointer.x) * 0.10
      pointer.y += (pointer.targetY - pointer.y) * 0.10
      pointer.velocityX *= 0.90
      pointer.velocityY *= 0.90

      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      context.clearRect(0, 0, width, height)
      context.globalCompositeOperation = 'lighter'
      context.lineCap = 'round'

      const normalizedPointerX = width ? (pointer.x / width) * 2 - 1 : 0
      const normalizedPointerY = height ? (pointer.y / height) * 2 - 1 : 0
      const cursorSpeed = clamp(Math.hypot(pointer.velocityX, pointer.velocityY) / 28, 0, 1)

      for (const particle of particles) {
        const depth = particle.depth
        if (!reducedMotion) {
          particle.x += particle.vx * delta
          particle.y += particle.vy * delta
        }

        if (particle.x < -20) particle.x = width + 20
        if (particle.x > width + 20) particle.x = -20
        if (particle.y < -20) particle.y = height + 20
        if (particle.y > height + 20) particle.y = -20

        const parallax = pointer.active ? DEPTH_PARALLAX[depth] : DEPTH_PARALLAX[depth] * 0.16
        const inertiaScale = 0.08 + depth * 0.07
        let screenX = particle.x - normalizedPointerX * parallax - pointer.velocityX * inertiaScale
        let screenY = particle.y - normalizedPointerY * parallax * 0.78 - pointer.velocityY * inertiaScale

        if (pointer.active && !reducedMotion) {
          const dx = screenX - pointer.x
          const dy = screenY - pointer.y
          const distance = Math.hypot(dx, dy)
          const influenceRadius = 118 + depth * 42
          if (distance > 0.01 && distance < influenceRadius) {
            const influence = 1 - distance / influenceRadius
            const displacement = influence * influence * (7 + depth * 7.5)
            screenX += (dx / distance) * displacement
            screenY += (dy / distance) * displacement
          }
        }

        const twinkleAmplitude = depth === 0 ? 0.12 : depth === 1 ? 0.18 : 0.22
        const twinkle = reducedMotion
          ? 0.92
          : 0.88 + Math.sin(time * particle.twinkle + particle.phase) * twinkleAmplitude
        let alpha = particle.alpha * twinkle * (1 + cursorSpeed * (0.035 + depth * 0.045))

        if (avoidRect) {
          const distanceToPanel = distanceFromRect(screenX, screenY, avoidRect)
          if (distanceToPanel === 0) alpha *= 0.08
          else if (distanceToPanel < 88) alpha *= 0.18 + (distanceToPanel / 88) * 0.58
        }

        if (Number.isFinite(particle.previousX) && Number.isFinite(particle.previousY) && !reducedMotion) {
          const trailAlpha = alpha * (0.035 + depth * 0.020 + cursorSpeed * 0.022)
          context.beginPath()
          context.moveTo(particle.previousX, particle.previousY)
          context.lineTo(screenX, screenY)
          context.strokeStyle = `rgba(73, 218, 242, ${trailAlpha})`
          context.lineWidth = 0.42 + depth * 0.13
          context.stroke()
        }

        const glowRadius = particle.radius * (2.5 + depth * 0.48) * particle.glow
        context.beginPath()
        context.arc(screenX, screenY, glowRadius, 0, Math.PI * 2)
        context.fillStyle = `rgba(50, 188, 226, ${alpha * 0.055 * particle.glow})`
        context.fill()

        context.beginPath()
        context.arc(screenX, screenY, particle.radius, 0, Math.PI * 2)
        context.fillStyle = starColor(particle.tone, alpha)
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
