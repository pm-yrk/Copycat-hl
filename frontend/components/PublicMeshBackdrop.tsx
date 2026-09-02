'use client'

import { useEffect, useRef } from 'react'

type RibbonKind = 'primary' | 'cross'
type Ripple = {
  x: number
  lineIndex: number
  kind: RibbonKind
  born: number
  strength: number
}

const VIEW_WIDTH = 1680
const VIEW_HEIGHT = 860
const PRIMARY_COUNT = 46
const CROSS_COUNT = 30

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}

function ribbonY(index: number, count: number, t: number, kind: RibbonKind) {
  const n = index / Math.max(1, count - 1)
  const offset = (n - .5) * (kind === 'primary' ? 180 : 145)
  const taper = Math.sin(Math.PI * t)
  const perspective = Math.pow(Math.max(0, taper), .74)

  if (kind === 'primary') {
    const base = 250 + 155 * Math.sin((t - .13) * Math.PI * 1.55) - 80 * Math.sin(t * Math.PI * 3.1)
    const fold = 116 * Math.sin((t * 2.1 + .12) * Math.PI) * taper
    return base + offset * perspective + fold * (n - .5) * 1.22
  }

  const base = 625 - 315 * t + 92 * Math.sin((t + .08) * Math.PI * 1.8)
  const fold = 92 * Math.cos((t * 2.35 + .2) * Math.PI) * taper
  return base + offset * perspective + fold * (n - .5)
}

export default function PublicMeshBackdrop({ variant = 'default' }: { variant?: 'home' | 'pricing' | 'login' | 'api' | 'default' }) {
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
      primaryGradient.addColorStop(0, 'rgba(57,239,181,0)')
      primaryGradient.addColorStop(.075, 'rgba(57,239,181,.25)')
      primaryGradient.addColorStop(.18, 'rgba(63,244,188,.94)')
      primaryGradient.addColorStop(.58, 'rgba(77,242,192,1)')
      primaryGradient.addColorStop(.88, 'rgba(55,224,174,.72)')
      primaryGradient.addColorStop(1, 'rgba(55,224,174,0)')
      crossGradient = context.createLinearGradient(0, 0, VIEW_WIDTH, 0)
      crossGradient.addColorStop(0, 'rgba(44,205,171,0)')
      crossGradient.addColorStop(.11, 'rgba(44,205,171,.36)')
      crossGradient.addColorStop(.48, 'rgba(52,226,184,.76)')
      crossGradient.addColorStop(.9, 'rgba(43,196,169,.34)')
      crossGradient.addColorStop(1, 'rgba(43,196,169,0)')
    }

    const nearestStrand = (x: number, y: number) => {
      const t = clamp(x / VIEW_WIDTH, 0, 1)
      let nearest = { distance: Number.POSITIVE_INFINITY, lineIndex: 0, kind: 'primary' as RibbonKind }
      for (let index = 0; index < PRIMARY_COUNT; index++) {
        const distance = Math.abs(ribbonY(index, PRIMARY_COUNT, t, 'primary') - y)
        if (distance < nearest.distance) nearest = { distance, lineIndex: index, kind: 'primary' }
      }
      for (let index = 0; index < CROSS_COUNT; index++) {
        const distance = Math.abs(ribbonY(index, CROSS_COUNT, t, 'cross') - y)
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
      const base = ribbonY(index, count, 0, kind)
      const firstY = base + displacement(0, base, 0, index, kind)
      context.beginPath()
      context.moveTo(0, firstY)
      let previousX = 0
      let previousY = firstY
      for (let step = 1; step <= steps; step++) {
        const t = step / steps
        const x = VIEW_WIDTH * t
        const baseY = ribbonY(index, count, t, kind)
        const y = baseY + displacement(x, baseY, t, index, kind)
        const middleX = (previousX + x) * .5
        const middleY = (previousY + y) * .5
        context.quadraticCurveTo(previousX, previousY, middleX, middleY)
        previousX = x
        previousY = y
      }
      context.lineTo(previousX, previousY)
    }

    const draw = () => {
      if (!canvas.width || !canvas.height || !primaryGradient || !crossGradient) return
      context.clearRect(0, 0, VIEW_WIDTH, VIEW_HEIGHT)
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
        return
      }
      const nearest = nearestStrand(x, y)
      pointerX = x
      pointerY = y
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
  }, [])

  return <div ref={backdropRef} className={'public-mesh public-mesh-' + variant + ' public-mesh-is-animated'} aria-hidden="true">
    <canvas ref={canvasRef} className="public-mesh-wave-canvas"/>
  </div>
}
