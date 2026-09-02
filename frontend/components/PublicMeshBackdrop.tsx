'use client'

import { useEffect, useRef } from 'react'

type Point = { x: number; y: number }

function spline(points: Point[]) {
  if (points.length < 2) return ''
  let d = `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[Math.min(points.length - 1, i + 2)]
    const c1x = p1.x + (p2.x - p0.x) / 6
    const c1y = p1.y + (p2.y - p0.y) / 6
    const c2x = p2.x - (p3.x - p1.x) / 6
    const c2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }
  return d
}

function ribbonPath(index: number, count: number, variant: 'primary' | 'cross') {
  const n = index / Math.max(1, count - 1)
  const offset = (n - .5) * (variant === 'primary' ? 180 : 145)
  const points: Point[] = []
  const steps = 18

  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const x = 1680 * t
    const taper = Math.sin(Math.PI * t)
    const perspective = Math.pow(taper, .74)

    if (variant === 'primary') {
      const base = 250 + 155 * Math.sin((t - .13) * Math.PI * 1.55) - 80 * Math.sin(t * Math.PI * 3.1)
      const fold = 116 * Math.sin((t * 2.1 + .12) * Math.PI) * taper
      const y = base + offset * perspective + fold * (n - .5) * 1.22
      points.push({ x, y })
    } else {
      const base = 625 - 315 * t + 92 * Math.sin((t + .08) * Math.PI * 1.8)
      const fold = 92 * Math.cos((t * 2.35 + .2) * Math.PI) * taper
      const y = base + offset * perspective + fold * (n - .5)
      points.push({ x, y })
    }
  }
  return spline(points)
}

export default function PublicMeshBackdrop({ variant = 'default' }: { variant?: 'home' | 'pricing' | 'login' | 'api' | 'default' }) {
  const backdropRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = backdropRef.current
    if (!node) return

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const mobileMotion = window.matchMedia('(max-width: 820px), (hover: none) and (pointer: coarse)')
    if (mobileMotion.matches) {
      node.style.setProperty('--mesh-scroll-y', '0px')
      node.style.setProperty('--mesh-scroll-x', '0px')
      node.style.setProperty('--mesh-scroll-tilt', '0deg')
      return
    }

    let frame = 0
    const updatePosition = () => {
      frame = 0
      const pageRange = Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
      const progress = Math.min(1, Math.max(0, window.scrollY / pageRange))
      node.style.setProperty('--mesh-scroll-y', `${(progress * 38).toFixed(2)}px`)
      node.style.setProperty('--mesh-scroll-x', `${(Math.sin(progress * Math.PI) * 9).toFixed(2)}px`)
      node.style.setProperty('--mesh-scroll-tilt', `${((progress - .5) * .42).toFixed(3)}deg`)
    }
    const schedulePosition = () => {
      if (!frame) frame = window.requestAnimationFrame(updatePosition)
    }

    updatePosition()
    window.addEventListener('scroll', schedulePosition, { passive: true })
    window.addEventListener('resize', schedulePosition)
    return () => {
      window.removeEventListener('scroll', schedulePosition)
      window.removeEventListener('resize', schedulePosition)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  const primaryCount = 46
  const crossCount = 30
  const strandGroups = 6
  const primary = Array.from({ length: primaryCount }, (_, i) => ({
    d: ribbonPath(i, primaryCount, 'primary'),
    opacity: .08 + .33 * Math.pow(Math.sin((i / (primaryCount - 1)) * Math.PI), 1.35),
  }))
  const cross = Array.from({ length: crossCount }, (_, i) => ({
    d: ribbonPath(i, crossCount, 'cross'),
    opacity: .045 + .19 * Math.pow(Math.sin((i / (crossCount - 1)) * Math.PI), 1.5),
  }))

  return <div ref={backdropRef} className={`public-mesh public-mesh-${variant} public-mesh-is-animated`} aria-hidden="true">
    <svg viewBox="0 0 1680 860" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`meshFade-${variant}`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="white" stopOpacity="0"/>
          <stop offset=".09" stopColor="white" stopOpacity=".76"/>
          <stop offset=".42" stopColor="white" stopOpacity="1"/>
          <stop offset=".82" stopColor="white" stopOpacity=".9"/>
          <stop offset="1" stopColor="white" stopOpacity="0"/>
        </linearGradient>
        <mask id={`meshMask-${variant}`}>
          <rect width="1680" height="860" fill={`url(#meshFade-${variant})`}/>
        </mask>
        <filter id={`meshGlow-${variant}`} x="-25%" y="-25%" width="150%" height="150%">
          <feGaussianBlur stdDeviation="5" result="blur"/>
        </filter>
      </defs>

      <g mask={`url(#meshMask-${variant})`} className="public-mesh-cross">
        {Array.from({ length: strandGroups }, (_, group) => <g key={`cross-group-${group}`} className={`public-mesh-strand-group public-mesh-strand-${group}`}>
          {cross.map((line, i) => i % strandGroups === group ? <path key={`c-${i}`} d={line.d} style={{ opacity: line.opacity }}/> : null)}
        </g>)}
      </g>
      <g mask={`url(#meshMask-${variant})`} className="public-mesh-ribbon">
        {Array.from({ length: strandGroups }, (_, group) => <g key={`primary-group-${group}`} className={`public-mesh-strand-group public-mesh-strand-${group}`}>
          {primary.map((line, i) => i % strandGroups === group ? <path key={`p-${i}`} d={line.d} style={{ opacity: line.opacity }}/> : null)}
        </g>)}
      </g>
      <g mask={`url(#meshMask-${variant})`} className="public-mesh-glow" filter={`url(#meshGlow-${variant})`}>
        <path d={ribbonPath(Math.floor(primaryCount * .47), primaryCount, 'primary')}/>
        <path d={ribbonPath(Math.floor(primaryCount * .54), primaryCount, 'primary')}/>
      </g>
      <g mask={`url(#meshMask-${variant})`} className="public-mesh-highlight">
        <path d={ribbonPath(Math.floor(primaryCount * .49), primaryCount, 'primary')}/>
        <path d={ribbonPath(Math.floor(primaryCount * .52), primaryCount, 'primary')}/>
      </g>
    </svg>
  </div>
}
