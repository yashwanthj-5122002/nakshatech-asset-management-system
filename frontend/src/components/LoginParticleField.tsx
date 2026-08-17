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
