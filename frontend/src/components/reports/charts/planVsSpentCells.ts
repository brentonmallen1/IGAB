/** Pure rules for Plan vs Spent's cells, totals and headline, apart from the
 * component so each branch is a one-line test. Every figure and verdict is
 * served (`over`, `active`, `chronic`, `running_month`, `categories_over`,
 * the totals); this only composes them. */
import type { CSSProperties } from 'react'
import type { PlanVsSpentCategory, PlanVsSpentMonth, PlanVsSpentReport } from '../../../types'
import { PRIVACY_MASK, toCents } from '../../../utils/money'
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

/** Overspend tint, scaled by how bad the figure was relative to the worst
 * overspend on screen — colour only where the server says "over". A few
 * cents past the plan is on plan, and is not tinted however it is signed. */
export function overspendStyle(
  figure: { over: boolean; variance: number },
  maxOver: number
): CSSProperties {
  if (!figure.over) return {}
  const pct = Math.round(Math.min(1, -figure.variance / maxOver) * 30) + 8
  return { background: `color-mix(in srgb, var(--chart-negative) ${pct}%, transparent)` }
}

/** The worst over-plan month on screen, the cells' tint's full scale. The
 *  Total column scales against its own worst (`worstTotalOverspend`): a
 *  year's overrun beside a month's would wash every cell out. */
export function worstOverspend(categories: PlanVsSpentCategory[]): number {
  let worst = 1
  for (const c of categories) {
    for (const m of c.monthly) if (m.over) worst = Math.max(worst, -m.variance)
  }
  return worst
}

export function worstTotalOverspend(categories: PlanVsSpentCategory[]): number {
  let worst = 1
  for (const c of categories) if (c.total.over) worst = Math.max(worst, -c.total.variance)
  return worst
}

/** Which way a month total went, by the cent: every category's verdict
 *  summed, so it carries no tolerance of its own — the categories' did. */
export function monthTotalTone(total: PlanVsSpentMonth): 'over' | 'under' | 'on' {
  const cents = toCents(total.variance)
  if (cents === 0) return 'on'
  return cents < 0 ? 'over' : 'under'
}

/**
 * The headline card for the window's served `total_variance`: which way the
 * window went against its plans, then by how much.
 *
 * The card read "Variance" over a signed figure, and the figure was raw
 * `total_assigned - total_spent` — so it disagreed with the rows beneath it
 * wherever an envelope was drained, and a reader had to remember which sign
 * meant over. The figure is the rows' verdicts summed now, and the label says
 * the direction in words.
 */
export function varianceHeadline(
  totalVariance: number,
  formatMoney: (amount: number) => string
): { label: string; value: string; over: boolean } {
  const cents = toCents(totalVariance)
  if (cents === 0) return { label: 'Against plan', value: 'On plan', over: false }
  return cents < 0
    ? { label: 'Over plan by', value: formatMoney(-totalVariance), over: true }
    : { label: 'Under plan by', value: formatMoney(totalVariance), over: false }
}

/** What a Total cell's title says of its share: the served percentage, or —
 *  with no plan to take a share of — "on plan" for a plan fully moved out
 *  with nothing spent past it (a mortgage assigned 1,500 and paid by a 1,500
 *  principal transfer), "no plan" for spending against none. Budget vs Actual
 *  printed "0.0%" for both. */
export function totalShareLabel(total: { variance_pct: number | null; over: boolean }): string {
  if (total.variance_pct === null) return total.over ? 'no plan' : 'on plan'
  const pct = Math.abs(total.variance_pct).toFixed(0)
  return total.variance_pct < 0 ? `${pct}% over` : `${pct}% under`
}

export interface PlanVsSpentHeadline {
  chronic: number
  /** The newest COMPLETE month and how many categories went over in it
   *  (served, `categories_over`); null when the window holds none. The
   *  running month is never "last month". */
  lastMonth: { month: string; over: number } | null
  /** The category over plan most often, the larger overrun breaking a tie.
   *  A sinking fund is never it: paying its bill is the plan working. */
  mostOver: { name: string; monthsOver: number; monthsActive: number } | null
}

/** "N chronic · N over in Aug · most over: X" — the question the report
 *  answers, in one line. */
export function planVsSpentHeadline(report: PlanVsSpentReport): PlanVsSpentHeadline {
  const newest = report.month_totals.filter((m) => !m.partial_month).at(-1)
  const overrun = (c: PlanVsSpentCategory) => c.months_over * c.avg_overspend
  const candidates = report.categories.filter((c) => c.months_over > 0 && !c.sinking_fund)
  const top = candidates.reduce<PlanVsSpentCategory | null>(
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
    lastMonth: newest ? { month: newest.month, over: newest.categories_over } : null,
    mostOver:
      top === null
        ? null
        : { name: top.category_name, monthsOver: top.months_over, monthsActive: top.months_active },
  }
}

/** The export's wide rows: one per category, one variance column per month,
 *  then the Total column's figures. */
export function exportRows(categories: PlanVsSpentCategory[]): Record<string, unknown>[] {
  return categories.map((c) => {
    const row: Record<string, unknown> = {
      category: c.category_name,
      group: c.category_group_name,
    }
    for (const cell of c.monthly) row[cell.month.slice(0, 7)] = cell.variance
    row.total_assigned = c.total.assigned
    row.total_moved_in = c.total.moved_in
    row.total_moved_out = c.total.moved_out
    row.total_planned = c.total.plan
    row.total_spent = c.total.spent
    row.total_variance = c.total.variance
    row.months_over = c.months_over
    row.chronic = c.chronic
    return row
  })
}
