/**
 * How the Day Patterns and Payday Effect panels read what the server sent.
 * Every figure is served — the per-day average (`avg_per_day`, divided by the
 * calendar weekdays in the window) and the payday medians — so this only
 * ranks and labels them, once, where a test can reach it.
 */
import type { DayPatternItem, PaydayEffectDay } from '../../../types'

/** The weekdays with the highest and lowest average day. Ranked by the
 *  per-day average, not the window's total: a window of five Saturdays and
 *  four Sundays gave Saturday a fifth more total for spending the same. */
export function busiestAndQuietest(
  days: readonly DayPatternItem[]
): { busiest: DayPatternItem; quietest: DayPatternItem } | null {
  const ranked = days.filter((d) => d.avg_per_day !== null)
  if (ranked.length === 0 || !ranked.some((d) => d.total !== 0)) return null
  const avg = (d: DayPatternItem) => d.avg_per_day ?? 0
  return {
    busiest: ranked.reduce((best, d) => (avg(d) > avg(best) ? d : best)),
    quietest: ranked.reduce((least, d) => (avg(d) < avg(least) ? d : least)),
  }
}

/** A weekday's axis label: three letters, which fit seven bars on a phone —
 *  "Wednesday" ran into its neighbours below 400px. The tooltip names it. */
export function shortDay(dayName: string): string {
  return dayName.slice(0, 3)
}

export interface PaydayBar {
  name: string
  offset: number
  spend: number
  paydays: number
  /** Above the typical day. Drawn in a second series colour, not a warning
   *  one: spending more after being paid is what pay is for, and the report
   *  describes when, not whether it is wrong. */
  aboveBaseline: boolean
}

export function paydayBars(days: readonly PaydayEffectDay[], baseline: number | null): PaydayBar[] {
  return days.map((d) => ({
    name: d.offset === 0 ? 'Payday' : `+${d.offset}`,
    offset: d.offset,
    spend: d.median_spend,
    paydays: d.paydays,
    aboveBaseline: baseline !== null && d.median_spend > baseline,
  }))
}

/** The day after payday with the highest median, or null with none. */
export function paydayPeak(days: readonly PaydayEffectDay[]): PaydayEffectDay | null {
  if (days.length === 0) return null
  return days.reduce((best, d) => (d.median_spend > best.median_spend ? d : best))
}
