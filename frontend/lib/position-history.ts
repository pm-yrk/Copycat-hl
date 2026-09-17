export type PositionSample = { ts_ms: number; position: number; price?: number }
export type PositionFrame = { ts_ms: number; assets: Record<string, [number, number | null]> }
const HISTORY_BASES = [
  `${(process.env.NEXT_PUBLIC_SNAPSHOT_BASE_URL || 'https://pub-b9e0279f5eb0496b99c7fa37329e6b53.r2.dev').replace(/\/+$/, '')}/position-history`,
  'https://raw.githubusercontent.com/pm-yrk/Copycat-hl/position-history',
]
const dayCache = new Map<string, PositionFrame[]>()

export function assetHistory(frames: PositionFrame[], asset: string, start: number, end: number): PositionSample[] {
  const points = new Map<number, PositionSample>()
  for (const frame of frames) {
    if (!Number.isFinite(frame?.ts_ms) || frame.ts_ms < start || frame.ts_ms > end || !frame.assets) continue
    const values = frame.assets[asset]
    // Absence is unknown here: never turn missing history into zero exposure.
    if (!values || typeof values[0] !== 'number' || !Number.isFinite(values[0])) continue
    points.set(frame.ts_ms, { ts_ms: frame.ts_ms, position: values[0], ...(typeof values[1] === 'number' && values[1] > 0 && Number.isFinite(values[1]) ? { price: values[1] } : {}) })
  }
  return [...points.values()].sort((a, b) => a.ts_ms - b.ts_ms)
}

export async function loadPositionHistory(rangeMs: number, signal: AbortSignal): Promise<PositionFrame[]> {
  const loadSource = async (base: string) => {
    const read = async (path: string) => {
      const response = await fetch(`${base}/${path}`, { signal, cache: 'no-store' })
      if (!response.ok) throw new Error('Position archive unavailable')
      return response.json()
    }
    const index = await read('index.json')
    if (index?.schema_version !== 1 || !Array.isArray(index.days)) throw new Error('Invalid position archive')
    const cutoff = new Date(Date.now() - rangeMs).toISOString().slice(0, 10)
    const days: string[] = index.days.filter((day: unknown) => typeof day === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(day) && day >= cutoff).slice(-32)
    const newest = days[days.length - 1]
    const frames: PositionFrame[] = []
    for (let i = 0; i < days.length; i += 4) {
      const batch = await Promise.all(days.slice(i, i + 4).map(async (day) => {
        const cacheKey = `${base}:${day}`
        if (day !== newest && dayCache.has(cacheKey)) return dayCache.get(cacheKey)!
        const payload = await read(`days/${day}.json`)
        if (payload?.schema_version !== 1 || !Array.isArray(payload.frames)) throw new Error('Invalid archived day')
        dayCache.set(cacheKey, payload.frames)
        return payload.frames as PositionFrame[]
      }))
      frames.push(...batch.flat())
    }
    return frames
  }
  const results = await Promise.allSettled(HISTORY_BASES.map(loadSource))
  const frames = results.flatMap((result) => result.status === 'fulfilled' ? result.value : [])
  if (!frames.length && results.every((result) => result.status === 'rejected')) {
    throw new Error('Position archive unavailable')
  }
  const byTimestamp = new Map<number, PositionFrame>()
  frames.forEach((frame) => { if (Number.isFinite(frame?.ts_ms)) byTimestamp.set(frame.ts_ms, frame) })
  return [...byTimestamp.values()].sort((a, b) => a.ts_ms - b.ts_ms)
}

export function positionChartPath(points: PositionSample[], minimum: number, span: number, start: number, end: number): string {
  return points.map((point, index) => {
    const x = (point.ts_ms - start) / Math.max(1, end - start) * 760
    const y = 250 - (point.position - minimum) / Math.max(1, span) * 250
    // Scheduled captures can be delayed. Longer holes remain visible gaps.
    const command = index > 0 && point.ts_ms - points[index - 1].ts_ms <= 30 * 60000 ? 'L' : 'M'
    return `${command} ${x.toFixed(2)} ${y.toFixed(2)}`
  }).join(' ')
}
