/** Pure rules for the Plan vs Reality matrix's cells and headline, apart from
 * the component so each branch is a one-line test. Every verdict is served
 * (`over`, `active`, `chronic`, `running_month`); this only composes them. */
import type { CSSProperties } from 'react'
import type { PlanRealityCategory, PlanRealityCell, PlanRealityReport } from '../../../types'
import { PRIVACY_MASK } from '../../../utils/money'
import { abbreviateValue } from './seasonalityScale'

/** An active cell's text: "−40" over plan, "+10" under, "0" on it.
 *
 * The sign goes on the ROUNDED figure. It went on the raw one, so a few cents
 * over read "−0" and a few under "+0" — a sign on nothing, which read as
 * an overspend too small to show rather than as on plan.
 *
 * Masked, every active cell reads the mask alone, zero included. The sign
 * went outside the mask ("−••••" / "+••••") and an on-plan month read a
 * literal "0", so overspending could be read straight off a grid whose title
 * and cards said a sign-less "$••••" — which is what PRIVACY_MASK exists to
 * prevent.
 *
 * The overspend tint and the "over" weight stay in privacy mode, on purpose:
 * like every chart's bar heights and the Budget page's overspent colour, they
 * show state rather than a figure, and privacy mode masks figures. */
export function cellLabel(variance: number, masked: boolean): string {
  if (masked) return PRIVACY_MASK
  const text = abbreviateValue(Math.abs(variance), false)
  if (text === '0') return '0'
  return variance < 0 ? `−${text}` : `+${text}`
}

/** Overspend tint, scaled by how bad the month was relative to the worst
 * overspend on screen — colour only where the server says "over". A few
 * cents past the plan is on plan, and is not tinted however it is signed. */
export function overspendStyle(cell: PlanRealityCell, maxOver: number): CSSProperties {
  if (!cell.over) return {}
  const pct = Math.round(Math.min(1, -cell.variance / maxOver) * 30) + 8
  return { background: `color-mix(in srgb, var(--chart-negative) ${pct}%, transparent)` }
}

/** The worst over-plan month on screen, the tint's full scale. */
export function worstOverspend(categories: PlanRealityCategory[]): number {
  let worst = 1
  for (const c of categories) {
    for (const m of c.monthly) if (m.over) worst = Math.max(worst, -m.variance)
  }
  return worst
}

export interface PlanRealityHeadline {
  chronic: number
  /** The newest COMPLETE month and how many categories went over in it; null
   *  when the window holds none. The running month is never "last month". */
  lastMonth: { month: string; over: number } | null
  /** The category over plan most often, the larger overrun breaking a tie.
   *  A sinking fund is never it: paying its bill is the plan working. */
  worst: { name: string; monthsOver: number; monthsActive: number } | null
}

/** "N chronic · N over last month · worst: X" — the matrix read in one line,
 *  which three totals cards (assigned, spent, a count) did not do. */
export function planRealityHeadline(report: PlanRealityReport): PlanRealityHeadline {
  const complete = report.months.filter((m) => m !== report.running_month)
  const newest = complete.length > 0 ? complete[complete.length - 1] : null
  const lastMonth =
    newest === null
      ? null
      : {
          month: newest,
          over: report.categories.filter((c) => c.monthly.some((m) => m.month === newest && m.over))
            .length,
        }
  const overrun = (c: PlanRealityCategory) => c.months_over * c.avg_overspend
  const candidates = report.categories.filter((c) => c.months_over > 0 && !c.sinking_fund)
  const top = candidates.reduce<PlanRealityCategory | null>(
    (best, c) =>
      best === null ||
      c.months_over > best.months_over ||
      (c.months_over === best.months_over && overrun(c) > overrun(best))
        ? c
        : best,
    null
  )
  return {
    chronic: report.chronic_count,
    lastMonth,
    worst:
      top === null
        ? null
        : { name: top.category_name, monthsOver: top.months_over, monthsActive: top.months_active },
  }
}
