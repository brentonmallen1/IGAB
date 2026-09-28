/**
 * A value axis whose negative side is only as deep as the data below zero.
 *
 * recharts' automatic domain ticks both sides of zero with one step, so a
 * single −$75 reconciliation adjustment on Income by Source bought a whole
 * −$5,500 band: a quarter of the plot spent on a sliver nobody could see,
 * and every paycheque drawn a quarter shorter. Here the step comes from the
 * larger side; a dip smaller than half a step gets a sliver of room and no
 * tick of its own, and a real one is rounded out to whole steps as before.
 *
 * Pure — the chart passes the values it draws — so every branch is a
 * one-line test. Spread the result on a recharts `<YAxis>` together with
 * `allowDataOverflow`, which stops recharts widening the domain again.
 */

export interface AxisScale {
  domain: [number, number]
  ticks: number[]
}

/** How many steps the larger side of zero is divided into. */
const INTERVALS = 4

/** The room, as a share of the axis, a small dip below zero is given. */
const SLIVER = 0.04

/** The smallest 1, 2, 2.5 or 5 × 10ⁿ at least `raw`. */
export function niceStep(raw: number): number {
  if (!Number.isFinite(raw) || raw <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  for (const m of [1, 2, 2.5, 5]) {
    if (m * magnitude >= raw) return m * magnitude
  }
  return 10 * magnitude
}

/** Division is float too: 0.3 / 0.1 is 2.9999999999999996. */
const EPS = 1e-9

/** Float-tidy `k × step`: 3 × 0.1 is 0.30000000000000004. */
function tick(k: number, step: number): number {
  return Number((k * step).toPrecision(12))
}

/** The domain and ticks for a money (or any value) axis over `values`. */
export function valueAxis(values: readonly number[]): AxisScale {
  const finite = values.filter(Number.isFinite)
  const lo = Math.min(0, ...finite)
  const hi = Math.max(0, ...finite)
  const step = niceStep(Math.max(hi, -lo) / INTERVALS)
  if (lo === 0 && hi === 0) {
    return { domain: [0, tick(INTERVALS, step)], ticks: range(0, INTERVALS, step) }
  }
  const top = hi > 0 ? tick(Math.ceil(hi / step - EPS), step) : 0
  let bottom: number
  if (-lo >= step / 2) bottom = tick(Math.floor(lo / step + EPS), step)
  else if (lo < 0) bottom = lo - (top - lo) * SLIVER
  else bottom = 0
  return {
    domain: [bottom, top],
    ticks: range(Math.ceil(bottom / step - EPS), Math.floor(top / step + EPS), step),
  }
}

function range(from: number, to: number, step: number): number[] {
  const out: number[] = []
  for (let k = from; k <= to; k++) out.push(tick(k, step))
  return out
}

/**
 * `valueAxis` for a stack drawn by sign (`MIXED_SIGN_STACK`): each row's
 * positives stack up from zero and its negatives down, so the extremes are
 * per-row sums by sign — not the largest single segment.
 */
export function stackedValueAxis(
  rows: readonly Record<string, string | number>[],
  keys: readonly string[]
): AxisScale {
  const extents = rows.flatMap((row) => {
    let up = 0
    let down = 0
    for (const key of keys) {
      const v = row[key]
      if (typeof v !== 'number') continue
      if (v > 0) up += v
      else down += v
    }
    return [up, down]
  })
  return valueAxis(extents)
}
