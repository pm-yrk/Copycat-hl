export default function LineBackdrop({ variant = 'default' }: { variant?: 'landing' | 'pricing' | 'login' | 'dashboard' | 'default' }) {
  const paths = Array.from({ length: 34 })
  return (
    <div className={`line-backdrop line-backdrop-${variant}`} aria-hidden="true">
      <svg viewBox="0 0 1440 620" preserveAspectRatio="none">
        <defs>
          <linearGradient id={`waveGradient-${variant}`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="rgba(35,233,157,0.02)" />
            <stop offset="48%" stopColor="rgba(35,233,157,0.72)" />
            <stop offset="100%" stopColor="rgba(55,223,229,0.04)" />
          </linearGradient>
          <filter id={`waveGlow-${variant}`} x="-20%" y="-80%" width="140%" height="260%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {paths.map((_, i) => {
          const y = variant === 'pricing' ? 60 + i * 8.5 : variant === 'login' ? 120 + i * 11 : 95 + i * 8
          const lift = variant === 'dashboard' ? 285 : variant === 'landing' ? 260 : variant === 'pricing' ? 250 : 310
          const end = variant === 'dashboard' ? 1420 - i * 3 : 1360 - i * 1.8
          const startX = variant === 'login' ? -110 + i * 3 : -70 + i * 4
          const startY = variant === 'pricing' ? 540 - i * 6 : variant === 'login' ? 595 - i * 4 : 500 - i * 3
          const c1x = variant === 'dashboard' ? 520 : 430
          const c2x = variant === 'pricing' ? 850 : variant === 'login' ? 720 : 900
          return (
            <path
              key={i}
              d={`M ${startX} ${startY} C ${c1x + i * 3} ${lift - i * 9}, ${c2x + i * 1.5} ${y - i * 4}, ${end} ${y + Math.sin(i / 3) * 12}`}
              stroke={`url(#waveGradient-${variant})`}
              filter={i % 9 === 0 ? `url(#waveGlow-${variant})` : undefined}
            />
          )
        })}
        {Array.from({ length: 26 }).map((_, i) => (
          <circle key={`d-${i}`} cx={240 + i * 38 + (i % 5) * 21} cy={120 + (i % 8) * 48} r={i % 7 === 0 ? 1.6 : 0.8} />
        ))}
      </svg>
    </div>
  )
}
