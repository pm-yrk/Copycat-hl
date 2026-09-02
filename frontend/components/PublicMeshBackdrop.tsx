'use client'

import { useEffect, useRef } from 'react'

type RibbonKind = 'primary' | 'cross'
type PublicVariant = 'home' | 'pricing' | 'login' | 'api' | 'default' | 'terms' | 'privacy' | 'risk' | 'links'
type Ripple = {
  x: number
  lineIndex: number
  kind: RibbonKind
  born: number
  strength: number
}
type Particle = {
  x: number
  y: number
  vx: number
  vy: number
  driftX: number
  driftY: number
  size: number
  alpha: number
}
type RibbonTheme = {
  primary: ReadonlyArray<readonly [number, string]>
  cross: ReadonlyArray<readonly [number, string]>
  particle: string
  density: number
}

const VIEW_WIDTH = 1680
const VIEW_HEIGHT = 860
const PRIMARY_COUNT = 46
const CROSS_COUNT = 30

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}

const RIBBON_THEMES: Record<PublicVariant, RibbonTheme> = {
  login: {
    primary: [[0, 'rgba(57,239,181,0)'], [.075, 'rgba(57,239,181,.25)'], [.18, 'rgba(63,244,188,.94)'], [.58, 'rgba(77,242,192,1)'], [.88, 'rgba(55,224,174,.72)'], [1, 'rgba(55,224,174,0)']],
    cross: [[0, 'rgba(44,205,171,0)'], [.11, 'rgba(44,205,171,.36)'], [.48, 'rgba(52,226,184,.76)'], [.9, 'rgba(43,196,169,.34)'], [1, 'rgba(43,196,169,0)']],
    particle: 'rgb(83,239,185)',
    density: .72,
  },
  home: {
    primary: [[0, 'rgba(47,228,166,0)'], [.07, 'rgba(47,228,166,.3)'], [.2, 'rgba(69,246,186,.96)'], [.56, 'rgba(91,250,204,1)'], [.88, 'rgba(52,224,176,.74)'], [1, 'rgba(52,224,176,0)']],
    cross: [[0, 'rgba(36,190,166,0)'], [.12, 'rgba(42,211,178,.32)'], [.5, 'rgba(58,229,190,.7)'], [.9, 'rgba(40,194,168,.28)'], [1, 'rgba(40,194,168,0)']],
    particle: 'rgb(86,242,190)',
    density: 1.08,
  },
  pricing: {
    primary: [[0, 'rgba(62,211,205,0)'], [.08, 'rgba(62,211,205,.26)'], [.2, 'rgba(83,232,215,.91)'], [.54, 'rgba(102,245,217,.98)'], [.89, 'rgba(57,203,193,.68)'], [1, 'rgba(57,203,193,0)']],
    cross: [[0, 'rgba(43,171,177,0)'], [.1, 'rgba(48,190,188,.28)'], [.5, 'rgba(62,215,199,.66)'], [.91, 'rgba(43,175,176,.26)'], [1, 'rgba(43,175,176,0)']],
    particle: 'rgb(103,224,211)',
    density: .92,
  },
  api: {
    primary: [[0, 'rgba(56,235,164,0)'], [.065, 'rgba(56,235,164,.31)'], [.19, 'rgba(78,255,181,.98)'], [.55, 'rgba(105,255,200,1)'], [.9, 'rgba(58,232,175,.72)'], [1, 'rgba(58,232,175,0)']],
    cross: [[0, 'rgba(43,200,161,0)'], [.09, 'rgba(43,200,161,.33)'], [.49, 'rgba(60,231,181,.76)'], [.91, 'rgba(45,197,162,.3)'], [1, 'rgba(45,197,162,0)']],
    particle: 'rgb(100,255,193)',
    density: 1.18,
  },
  default: {
    primary: [[0, 'rgba(43,198,166,0)'], [.08, 'rgba(43,198,166,.23)'], [.2, 'rgba(58,221,180,.86)'], [.56, 'rgba(75,235,194,.94)'], [.89, 'rgba(43,196,165,.62)'], [1, 'rgba(43,196,165,0)']],
    cross: [[0, 'rgba(35,160,155,0)'], [.11, 'rgba(35,160,155,.24)'], [.5, 'rgba(48,194,171,.57)'], [.9, 'rgba(35,163,155,.22)'], [1, 'rgba(35,163,155,0)']],
    particle: 'rgb(78,216,180)',
    density: .82,
  },
  terms: {
    primary: [[0, 'rgba(55,199,190,0)'], [.08, 'rgba(55,199,190,.23)'], [.2, 'rgba(73,222,203,.85)'], [.55, 'rgba(89,235,211,.93)'], [.9, 'rgba(51,190,184,.6)'], [1, 'rgba(51,190,184,0)']],
    cross: [[0, 'rgba(39,157,163,0)'], [.1, 'rgba(39,157,163,.23)'], [.5, 'rgba(54,190,182,.55)'], [.9, 'rgba(39,157,163,.2)'], [1, 'rgba(39,157,163,0)']],
    particle: 'rgb(91,217,203)',
    density: .72,
  },
  privacy: {
    primary: [[0, 'rgba(52,213,180,0)'], [.08, 'rgba(52,213,180,.25)'], [.2, 'rgba(71,236,196,.88)'], [.55, 'rgba(93,246,211,.95)'], [.89, 'rgba(50,205,178,.64)'], [1, 'rgba(50,205,178,0)']],
    cross: [[0, 'rgba(37,170,158,0)'], [.1, 'rgba(37,170,158,.24)'], [.5, 'rgba(54,205,179,.58)'], [.9, 'rgba(37,170,158,.22)'], [1, 'rgba(37,170,158,0)']],
    particle: 'rgb(86,231,196)',
    density: .78,
  },
  risk: {
    primary: [[0, 'rgba(73,224,165,0)'], [.08, 'rgba(73,224,165,.27)'], [.19, 'rgba(91,244,180,.91)'], [.55, 'rgba(115,250,201,.97)'], [.9, 'rgba(65,210,165,.66)'], [1, 'rgba(65,210,165,0)']],
    cross: [[0, 'rgba(47,181,147,0)'], [.1, 'rgba(47,181,147,.27)'], [.5, 'rgba(67,216,167,.62)'], [.9, 'rgba(47,181,147,.23)'], [1, 'rgba(47,181,147,0)']],
    particle: 'rgb(109,238,184)',
    density: .84,
  },
  links: {
    primary: [[0, 'rgba(51,199,201,0)'], [.08, 'rgba(51,199,201,.24)'], [.19, 'rgba(70,223,215,.87)'], [.55, 'rgba(91,238,222,.95)'], [.9, 'rgba(48,190,194,.63)'], [1, 'rgba(48,190,194,0)']],
    cross: [[0, 'rgba(37,158,170,0)'], [.1, 'rgba(37,158,170,.24)'], [.5, 'rgba(53,193,191,.58)'], [.9, 'rgba(37,158,170,.22)'], [1, 'rgba(37,158,170,0)']],
    particle: 'rgb(83,219,211)',
    density: .76,
  },
}

const VARIANT_SEEDS: Record<PublicVariant, number> = {
  home: 1207,
  pricing: 2341,
  login: 3499,
  api: 4679,
  default: 5861,
  terms: 6971,
  privacy: 8087,
  risk: 9137,
  links: 10259,
}

function createParticles(variant: PublicVariant, count: number) {
  if (count <= 0) return [] as Particle[]
  let state = VARIANT_SEEDS[variant] >>> 0
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0
    return state / 4294967296
  }
  return Array.from({ length: count }, () => {
    const driftX = (random() - .5) * 4.2
    const driftY = -1.5 - random() * 4.3
    return {
      x: random() * VIEW_WIDTH,
      y: random() * VIEW_HEIGHT,
      vx: driftX,
      vy: driftY,
      driftX,
      driftY,
      size: .28 + random() * .58,
      alpha: .14 + random() * .3,
    }
  })
}

function ribbonY(index: number, count: number, t: number, kind: RibbonKind, variant: PublicVariant) {
  const n = index / Math.max(1, count - 1)
  const spread = variant === 'pricing' ? .92 : variant === 'api' ? .86 : variant === 'default' ? .8 : 1
  const offset = (n - .5) * (kind === 'primary' ? 180 : 145) * spread
  const taper = Math.sin(Math.PI * t)
  const perspective = Math.pow(Math.max(0, taper), .74)

  if (variant === 'login') {
    if (kind === 'primary') {
      const base = 250 + 155 * Math.sin((t - .13) * Math.PI * 1.55) - 80 * Math.sin(t * Math.PI * 3.1)
      const fold = 116 * Math.sin((t * 2.1 + .12) * Math.PI) * taper
      return base + offset * perspective + fold * (n - .5) * 1.22
    }
    const base = 625 - 315 * t + 92 * Math.sin((t + .08) * Math.PI * 1.8)
    const fold = 92 * Math.cos((t * 2.35 + .2) * Math.PI) * taper
    return base + offset * perspective + fold * (n - .5)
  }

  if (variant === 'home') {
    if (kind === 'primary') {
      const base = 585 - 335 * t + 74 * Math.sin((t - .04) * Math.PI * 1.72) - 38 * Math.sin(t * Math.PI * 3.4)
      const fold = 128 * Math.sin((t * 1.86 + .2) * Math.PI) * taper
      return base + offset * perspective * 1.08 + fold * (n - .5)
    }
    const base = 178 + 292 * t + 72 * Math.sin((t + .16) * Math.PI * 1.48)
    const fold = 78 * Math.cos((t * 2.05 + .12) * Math.PI) * taper
    return base + offset * perspective * .88 + fold * (n - .5)
  }

  if (variant === 'pricing') {
    if (kind === 'primary') {
      const base = 570 - 250 * Math.sin(Math.PI * t) + 42 * Math.sin(t * Math.PI * 3)
      const fold = 68 * Math.sin((t * 2 + .16) * Math.PI) * taper
      return base + offset * perspective + fold * (n - .5)
    }
    const base = 178 + 208 * Math.sin(Math.PI * t) - 34 * Math.sin(t * Math.PI * 2)
    const fold = 58 * Math.cos((t * 1.8 + .24) * Math.PI) * taper
    return base + offset * perspective * .86 + fold * (n - .5)
  }

  if (variant === 'api') {
    if (kind === 'primary') {
      const base = 684 - 470 * t + 47 * Math.sin(t * Math.PI * 4)
      const fold = 78 * Math.sin((t * 2.7 + .1) * Math.PI) * taper
      return base + offset * perspective + fold * (n - .5)
    }
    const base = 112 + 486 * t + 39 * Math.sin((t + .08) * Math.PI * 3)
    const fold = 66 * Math.cos((t * 2.55 + .2) * Math.PI) * taper
    return base + offset * perspective * .82 + fold * (n - .5)
  }

  if (variant === 'terms') {
    if (kind === 'primary') {
      const base = 590 - 265 * t + 58 * Math.sin((t + .08) * Math.PI * 2.1)
      const fold = 82 * Math.sin((t * 1.75 + .14) * Math.PI) * taper
      return base + offset * perspective * .9 + fold * (n - .5)
    }
    const base = 170 + 160 * t + 76 * Math.sin((t + .1) * Math.PI * 1.7)
    return base + offset * perspective * .72 + 44 * Math.cos(t * Math.PI * 2.1) * taper * (n - .5)
  }

  if (variant === 'privacy') {
    if (kind === 'primary') {
      const base = 298 + 190 * Math.sin((t - .08) * Math.PI * 1.28) - 46 * Math.sin(t * Math.PI * 3)
      return base + offset * perspective * .94 + 86 * Math.sin((t * 2.2 + .1) * Math.PI) * taper * (n - .5)
    }
    const base = 610 - 188 * Math.sin((t + .04) * Math.PI * 1.35) - 132 * t
    return base + offset * perspective * .8 + 62 * Math.cos((t * 2 + .16) * Math.PI) * taper * (n - .5)
  }

  if (variant === 'risk') {
    if (kind === 'primary') {
      const base = 670 - 438 * t + 62 * Math.sin((t + .03) * Math.PI * 2.55)
      return base + offset * perspective * .88 + 92 * Math.sin((t * 2.45 + .08) * Math.PI) * taper * (n - .5)
    }
    const base = 154 + 352 * t - 55 * Math.sin(t * Math.PI * 2.2)
    return base + offset * perspective * .76 + 54 * Math.cos((t * 2.2 + .18) * Math.PI) * taper * (n - .5)
  }

  if (variant === 'links') {
    if (kind === 'primary') {
      const base = 515 - 205 * Math.sin((t + .04) * Math.PI) - 102 * t + 40 * Math.sin(t * Math.PI * 3.2)
      return base + offset * perspective * .92 + 74 * Math.sin((t * 1.9 + .18) * Math.PI) * taper * (n - .5)
    }
    const base = 212 + 126 * Math.sin((t - .12) * Math.PI * 1.45) + 180 * t
    return base + offset * perspective * .78 + 50 * Math.cos((t * 2.15 + .12) * Math.PI) * taper * (n - .5)
  }

  if (kind === 'primary') {
    const base = 520 - 68 * Math.sin(Math.PI * t) + 48 * Math.sin(t * Math.PI * 2.2)
    return base + offset * perspective + 56 * Math.sin((t * 1.8 + .16) * Math.PI) * taper * (n - .5)
  }
  const base = 245 + 60 * Math.sin(Math.PI * t) - 38 * Math.sin(t * Math.PI * 2)
  return base + offset * perspective * .72 + 42 * Math.cos((t * 2 + .2) * Math.PI) * taper * (n - .5)
}

export default function PublicMeshBackdrop({ variant = 'default' }: { variant?: PublicVariant }) {
  const backdropRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const node = backdropRef.current
    const canvas = canvasRef.current
    if (!node || !canvas) return

    const context = canvas.getContext('2d', { alpha: true })
    if (!context) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const mobileView = window.matchMedia('(max-width: 820px), (hover: none) and (pointer: coarse)')
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)')
    let primaryGradient: CanvasGradient | null = null
    let crossGradient: CanvasGradient | null = null
    let frame = 0
    let previousFrameAt = 0
    let simulationTime = 0
    let lastScrollY = window.scrollY
    let scrollEnergy = 0
    let outerX = 0
    let outerY = 0
    let outerTilt = 0
    let outerVelocityX = 0
    let outerVelocityY = 0
    let outerVelocityTilt = 0
    let pointerX = VIEW_WIDTH * .5
    let pointerY = VIEW_HEIGHT * .5
    let pointerLine = 0
    let pointerKind: RibbonKind = 'primary'
    let pointerStrength = 0
    let pointerActive = false
    let lastPointerX = pointerX
    let lastPointerY = pointerY
    let lastPointerAt = 0
    let lastRippleAt = 0
    let ripples: Ripple[] = []
    const theme = RIBBON_THEMES[variant]
    const particleCount = Math.round((mobileView.matches ? 28 : 50) * theme.density)
    const particles = createParticles(variant, particleCount)
    let particlePointerActive = false

    const setPhysics = () => {
      node.style.setProperty('--mesh-physics-x', outerX.toFixed(2) + 'px')
      node.style.setProperty('--mesh-physics-y', outerY.toFixed(2) + 'px')
      node.style.setProperty('--mesh-physics-tilt', outerTilt.toFixed(3) + 'deg')
    }

    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      const pixelRatio = Math.min(window.devicePixelRatio || 1, mobileView.matches ? 1.15 : 1.4)
      const width = Math.max(1, Math.round(rect.width * pixelRatio))
      const height = Math.max(1, Math.round(rect.height * pixelRatio))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      context.setTransform(width / VIEW_WIDTH, 0, 0, height / VIEW_HEIGHT, 0, 0)
      context.imageSmoothingEnabled = true
      context.imageSmoothingQuality = 'high'
      primaryGradient = context.createLinearGradient(0, 0, VIEW_WIDTH, 0)
      for (const [offset, colour] of theme.primary) primaryGradient.addColorStop(offset, colour)
      crossGradient = context.createLinearGradient(0, 0, VIEW_WIDTH, 0)
      for (const [offset, colour] of theme.cross) crossGradient.addColorStop(offset, colour)
    }

    const nearestStrand = (x: number, y: number) => {
      const t = clamp(x / VIEW_WIDTH, 0, 1)
      let nearest = { distance: Number.POSITIVE_INFINITY, lineIndex: 0, kind: 'primary' as RibbonKind }
      for (let index = 0; index < PRIMARY_COUNT; index++) {
        const distance = Math.abs(ribbonY(index, PRIMARY_COUNT, t, 'primary', variant) - y)
        if (distance < nearest.distance) nearest = { distance, lineIndex: index, kind: 'primary' }
      }
      for (let index = 0; index < CROSS_COUNT; index++) {
        const distance = Math.abs(ribbonY(index, CROSS_COUNT, t, 'cross', variant) - y)
        if (distance < nearest.distance) nearest = { distance, lineIndex: index, kind: 'cross' }
      }
      return nearest
    }

    const displacement = (x: number, baseY: number, t: number, index: number, kind: RibbonKind) => {
      const count = kind === 'primary' ? PRIMARY_COUNT : CROSS_COUNT
      const n = index / Math.max(1, count - 1)
      const taper = Math.pow(Math.sin(Math.PI * t), .72)
      const phase = n * 3.4 + (kind === 'primary' ? 0 : 1.7)
      const waterScale = kind === 'primary' ? 1 : .82
      let amount = (
        Math.sin(t * 7.4 - simulationTime * .52 + phase) * 2.35
        + Math.sin(t * 15.8 + simulationTime * .27 + phase * .63) * .92
      ) * (.34 + taper * .66) * waterScale

      amount += scrollEnergy
        * Math.sin(t * 6.1 - simulationTime * .84 + phase)
        * taper
        * (kind === 'primary' ? .46 : .32)

      if (pointerActive && pointerKind === kind) {
        const xDistance = (x - pointerX) / 118
        const lineDistance = (index - pointerLine) / 2.45
        const envelope = Math.exp(-(xDistance * xDistance)) * Math.exp(-(lineDistance * lineDistance))
        const pull = clamp(pointerY - baseY, -24, 24)
        amount += pull * .48 * pointerStrength * envelope
      }

      for (const ripple of ripples) {
        if (ripple.kind !== kind) continue
        const age = simulationTime - ripple.born
        if (age < 0 || age > 5.2) continue
        const lineDistance = (index - ripple.lineIndex) / 2.7
        const lineEnvelope = Math.exp(-(lineDistance * lineDistance))
        if (lineEnvelope < .008) continue
        const distance = Math.abs(x - ripple.x)
        const front = age * 275
        const width = 72 + age * 19
        const frontEnvelope = Math.exp(-Math.pow((distance - front) / width, 2))
        const decay = Math.exp(-age / 3.35)
        amount += Math.cos((distance - front) * .046)
          * 10.5
          * ripple.strength
          * lineEnvelope
          * frontEnvelope
          * decay
          * taper
      }
      return amount
    }

    const traceStrand = (index: number, count: number, kind: RibbonKind, steps: number) => {
      const base = ribbonY(index, count, 0, kind, variant)
      const firstY = base + displacement(0, base, 0, index, kind)
      context.beginPath()
      context.moveTo(0, firstY)
      let previousX = 0
      let previousY = firstY
      for (let step = 1; step <= steps; step++) {
        const t = step / steps
        const x = VIEW_WIDTH * t
        const baseY = ribbonY(index, count, t, kind, variant)
        const y = baseY + displacement(x, baseY, t, index, kind)
        const middleX = (previousX + x) * .5
        const middleY = (previousY + y) * .5
        context.quadraticCurveTo(previousX, previousY, middleX, middleY)
        previousX = x
        previousY = y
      }
      context.lineTo(previousX, previousY)
    }

    const updateParticles = (elapsed: number) => {
      if (!particles.length) return
      const frameScale = elapsed * 60
      for (const particle of particles) {
        particle.vx += (particle.driftX - particle.vx) * .018 * frameScale
        particle.vy += (particle.driftY - particle.vy) * .018 * frameScale
        particle.x += particle.vx * elapsed
        particle.y += (particle.vy + scrollEnergy * .22) * elapsed

        if (particlePointerActive) {
          const dx = particle.x - pointerX
          const dy = particle.y - pointerY
          const distance = Math.hypot(dx, dy)
          const radius = 155
          if (distance > .01 && distance < radius) {
            const response = Math.pow(1 - distance / radius, 2)
            particle.x += (dx / distance) * response * 92 * elapsed
            particle.y += (dy / distance) * response * 92 * elapsed
            particle.vx += (dx / distance) * response * 24 * elapsed
            particle.vy += (dy / distance) * response * 24 * elapsed
          }
        }

        const margin = 24
        if (particle.x < -margin) particle.x = VIEW_WIDTH + margin
        else if (particle.x > VIEW_WIDTH + margin) particle.x = -margin
        if (particle.y < -margin) particle.y = VIEW_HEIGHT + margin
        else if (particle.y > VIEW_HEIGHT + margin) particle.y = -margin
      }
    }

    const drawParticles = () => {
      if (!particles.length) return
      context.fillStyle = theme.particle
      for (const particle of particles) {
        context.globalAlpha = particle.alpha
        context.beginPath()
        context.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2)
        context.fill()
      }
      context.globalAlpha = 1
    }

    const draw = () => {
      if (!canvas.width || !canvas.height || !primaryGradient || !crossGradient) return
      context.clearRect(0, 0, VIEW_WIDTH, VIEW_HEIGHT)
      drawParticles()
      context.lineCap = 'round'
      context.lineJoin = 'round'
      const steps = mobileView.matches ? 60 : 86

      for (let index = 0; index < CROSS_COUNT; index++) {
        const center = Math.pow(Math.sin((index / (CROSS_COUNT - 1)) * Math.PI), 1.5)
        traceStrand(index, CROSS_COUNT, 'cross', steps)
        context.strokeStyle = crossGradient
        context.lineWidth = .72 + center * .34
        context.globalAlpha = .065 + center * .22
        context.stroke()
      }

      for (let index = 0; index < PRIMARY_COUNT; index++) {
        const center = Math.pow(Math.sin((index / (PRIMARY_COUNT - 1)) * Math.PI), 1.35)
        traceStrand(index, PRIMARY_COUNT, 'primary', steps)
        if (center > .54) {
          context.strokeStyle = primaryGradient
          context.lineWidth = 3.15
          context.globalAlpha = center * .055
          context.stroke()
        }
        context.strokeStyle = primaryGradient
        context.lineWidth = .8 + center * .56
        context.globalAlpha = .095 + center * .4
        context.stroke()
      }
      context.globalAlpha = 1
    }

    const animate = (now: number) => {
      const elapsed = previousFrameAt ? clamp((now - previousFrameAt) / 1000, 0, .034) : 1 / 60
      previousFrameAt = now
      simulationTime += elapsed
      scrollEnergy *= Math.pow(.973, elapsed * 60)
      ripples = ripples.filter(ripple => simulationTime - ripple.born < 5.2)

      const targetX = pointerActive ? ((pointerX / VIEW_WIDTH) - .5) * 5.5 : 0
      const targetY = (pointerActive ? ((pointerY / VIEW_HEIGHT) - .5) * 2.4 : 0) + scrollEnergy * .34
      const targetTilt = pointerActive ? ((pointerX / VIEW_WIDTH) - .5) * .14 : 0
      const frameScale = elapsed * 60
      outerVelocityX = (outerVelocityX + (targetX - outerX) * .025 * frameScale) * Math.pow(.88, frameScale)
      outerVelocityY = (outerVelocityY + (targetY - outerY) * .024 * frameScale) * Math.pow(.88, frameScale)
      outerVelocityTilt = (outerVelocityTilt + (targetTilt - outerTilt) * .022 * frameScale) * Math.pow(.88, frameScale)
      outerX += outerVelocityX * frameScale
      outerY += outerVelocityY * frameScale
      outerTilt += outerVelocityTilt * frameScale
      setPhysics()
      updateParticles(elapsed)
      draw()
      frame = window.requestAnimationFrame(animate)
    }

    const onPointerMove = (event: PointerEvent) => {
      if (!finePointer.matches || event.pointerType === 'touch') return
      const rect = canvas.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      const x = ((event.clientX - rect.left) / rect.width) * VIEW_WIDTH
      const y = ((event.clientY - rect.top) / rect.height) * VIEW_HEIGHT
      if (x < 0 || x > VIEW_WIDTH || y < 0 || y > VIEW_HEIGHT) {
        pointerActive = false
        particlePointerActive = false
        return
      }
      pointerX = x
      pointerY = y
      particlePointerActive = particles.length > 0
      const nearest = nearestStrand(x, y)
      pointerLine = nearest.lineIndex
      pointerKind = nearest.kind
      pointerStrength = clamp(1 - nearest.distance / 112, 0, 1)
      pointerActive = pointerStrength > .02
      const now = performance.now()
      const elapsed = Math.max(12, now - lastPointerAt)
      const travelled = Math.hypot(x - lastPointerX, y - lastPointerY)
      const speed = travelled / elapsed * 1000
      if (pointerActive && now - lastRippleAt > 42 && travelled > 4) {
        ripples.push({
          x,
          lineIndex: nearest.lineIndex,
          kind: nearest.kind,
          born: simulationTime,
          strength: clamp(.58 + speed / 1350, .58, 1.45),
        })
        if (ripples.length > 14) ripples.splice(0, ripples.length - 14)
        lastRippleAt = now
      }
      lastPointerX = x
      lastPointerY = y
      lastPointerAt = now
    }

    const releasePointer = () => {
      pointerActive = false
      particlePointerActive = false
      pointerStrength = 0
    }

    const onScroll = () => {
      const nextScrollY = window.scrollY
      const delta = clamp(nextScrollY - lastScrollY, -140, 140)
      lastScrollY = nextScrollY
      scrollEnergy = clamp(scrollEnergy - delta * .055, -16, 16)
    }

    const onResize = () => {
      lastScrollY = window.scrollY
      resizeCanvas()
    }

    resizeCanvas()
    setPhysics()
    if (reducedMotion.matches) {
      draw()
    } else {
      frame = window.requestAnimationFrame(animate)
    }

    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resizeCanvas) : null
    resizeObserver?.observe(canvas)
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    window.addEventListener('pointerleave', releasePointer)
    window.addEventListener('blur', releasePointer)
    window.addEventListener('resize', onResize)

    return () => {
      resizeObserver?.disconnect()
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerleave', releasePointer)
      window.removeEventListener('blur', releasePointer)
      window.removeEventListener('resize', onResize)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [variant])

  return <div ref={backdropRef} className={'public-mesh public-mesh-' + variant + ' public-mesh-is-animated'} aria-hidden="true">
    <canvas ref={canvasRef} className="public-mesh-wave-canvas"/>
  </div>
}
