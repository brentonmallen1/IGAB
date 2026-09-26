/**
 * Cash Projection's chart rows, key, tooltip and warning — the presentational
 * composition of the served bands (`domain/cash_projection.py`).
 *
 * **Bands are ranges, not stacks.** The chart stacked p90 on an opaque
 * `--bg-primary` "eraser" area of p10 (and p75 on p25): the shading ran from
 * zero up to p90, the eraser painted a block over it that only matched the
 * page on one surface, p10 itself was never drawn, and the y-axis was sized by
 * the stacked sum — so it clipped the low band exactly where a dip below zero
 * would show. A row now carries each band as `[low, high]` for recharts'
 * range areas, and the axis spans the values themselves.
 *
 * **One vocabulary.** The key said "Likely range (10–90%)" beside one swatch
 * while the info panel called 25–75 "likely" and 10–90 "most scenarios", and
 * the tooltip printed raw `p10`/`p25`. The names below are the only ones the
 * chart, key, tooltip and warning use.
 */
import type { CashProjectionPoint, CashProjectionReport } from '../../../types'

export interface ProjectionRow {
  /** Axis label. */
  date: string
  fullDate: string
  /** The 10–90% band, [p10, p90]. */
  outer: [number, number]
  /** The 25–75% band, [p25, p75]. */
  inner: [number, number]
  p10: number
  p25: number
  p50: number
  p75: number
  p90: number
  deterministic: number
}

export function projectionRows(
  points: CashProjectionPoint[],
  formatLabel: (isoDate: string) => string
): ProjectionRow[] {
  return points.map((p) => ({
    date: formatLabel(p.date),
    fullDate: p.date,
    outer: [p.p10, p.p90],
    inner: [p.p25, p.p75],
    p10: p.p10,
    p25: p.p25,
    p50: p.p50,
    p75: p.p75,
    p90: p.p90,
    deterministic: p.deterministic,
  }))
}

/** Fill opacity of each band's own area. The inner band is drawn over the
 *  outer one, so where it sits both layers show. */
const FILL = { outer: 0.14, inner: 0.22 } as const

export interface BandStyle {
  label: string
  /** The `<Area>`'s fillOpacity. */
  fillOpacity: number
  /** What the band looks like on the chart, for the key's swatch: the inner
   *  band is its own layer composited over the outer one. */
  swatchOpacity: number
}

export const PROJECTION_BANDS: { outer: BandStyle; inner: BandStyle } = {
  inner: {
    label: 'Middle half (25–75%)',
    fillOpacity: FILL.inner,
    swatchOpacity: 1 - (1 - FILL.outer) * (1 - FILL.inner),
  },
  outer: {
    label: '8 in 10 (10–90%)',
    fillOpacity: FILL.outer,
    swatchOpacity: FILL.outer,
  },
}

export const MEDIAN_LABEL = 'Median'
export const SCHEDULED_LABEL = 'Scheduled only'

export interface ProjectionTooltipEntry {
  name: string
  value: number
  color?: string
}

/** One day's tooltip, highest first: the band edges by how many paths end
 *  past them, the median, and the scheduled-only line. */
export function projectionTooltipEntries(row: ProjectionRow): ProjectionTooltipEntry[] {
  return [
    { name: '1 in 10 high', value: row.p90 },
    { name: '1 in 4 high', value: row.p75 },
    { name: MEDIAN_LABEL, value: row.p50, color: 'var(--accent-color)' },
    { name: '1 in 4 low', value: row.p25 },
    { name: '1 in 10 low', value: row.p10 },
    { name: SCHEDULED_LABEL, value: row.deterministic, color: 'var(--text-muted)' },
  ]
}

export type ProjectionWarning =
  /** The median is below zero by `date`: more likely than not. */
  | { kind: 'likely'; date: string; lead: string }
  /** Only the 1-in-10 low band is: possible, and worth saying so. */
  | { kind: 'possible'; date: string; lead: string }

/** Which warning to show, if any. The median's crossing wins — it is the
 *  stronger claim — and the low band's alone gets the softer line. A warning
 *  on the median alone was the seed's: a budget whose median brushed zero
 *  read "goes negative" on most days and not on the rest. `lead` is followed
 *  by the formatted zero, "by", and the date. */
export function projectionWarning(
  report: Pick<CashProjectionReport, 'goes_negative_date' | 'p10_negative_date'> | undefined
): ProjectionWarning | null {
  if (report?.goes_negative_date) {
    return {
      kind: 'likely',
      date: report.goes_negative_date,
      lead: 'More likely than not to be below',
    }
  }
  if (report?.p10_negative_date) {
    return {
      kind: 'possible',
      date: report.p10_negative_date,
      lead: 'About a 1 in 10 chance of dipping below',
    }
  }
  return null
}
