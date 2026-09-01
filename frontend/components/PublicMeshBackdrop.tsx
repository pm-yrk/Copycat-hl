function makeRibbon(offset: number, phase: number, scale = 1) {
  const pts: string[] = []
  const steps = 72
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const x = 1600 * t
    const envelope = Math.sin(Math.PI * t)
    const wave = Math.sin(t * Math.PI * 2.15 + phase) * 74 * envelope
    const bend = -220 * Math.pow(t - 0.54, 2) + 76
    const y = 250 + bend + wave * scale + offset
    pts.push(`${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
  }
  return pts.join(' ')
}

function makeSweep(offset: number, phase: number) {
  const pts: string[] = []
  const steps = 64
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const x = 1600 * t
    const envelope = Math.sin(Math.PI * t)
    const y = 650 - 330 * t + Math.sin(t * Math.PI * 1.6 + phase) * 54 * envelope + offset
    pts.push(`${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
  }
  return pts.join(' ')
}

export default function PublicMeshBackdrop({ variant = 'default' }: { variant?: 'home' | 'pricing' | 'login' | 'api' | 'default' }) {
  const ribbon = Array.from({ length: 21 }, (_, i) => makeRibbon((i - 10) * 8.5, i * 0.035, 1 - Math.abs(i - 10) * 0.012))
  const sweep = Array.from({ length: 14 }, (_, i) => makeSweep((i - 7) * 10.5, i * 0.025))
  return <div className={`public-mesh public-mesh-${variant}`} aria-hidden="true">
    <svg viewBox="0 0 1600 820" preserveAspectRatio="none">
      <g className="public-mesh-ribbon">{ribbon.map((d, i) => <path d={d} key={`r-${i}`} />)}</g>
      <g className="public-mesh-sweep">{sweep.map((d, i) => <path d={d} key={`s-${i}`} />)}</g>
    </svg>
  </div>
}
