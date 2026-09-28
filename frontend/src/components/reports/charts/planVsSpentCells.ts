/** Pure rules for Plan vs Spent's cells, totals and headline, apart from the
 * component so each branch is a one-line test. Every figure and verdict is
 * served (`over`, `active`, `chronic`, `running_month`, `categories_over`,
 * the totals — backend `domain/plan.py`); this only composes them. */
import type { CSSProperties } from 'react'
import type {
  PlanVsSpentCategory,
  PlanVsSpentFigures,
  PlanVsSpentMonth,
  PlanVsSpentReport,
} from '../../../types'
import { PRIVACY_MASK, toCents } from '../../../utils/money'
import { abbreviateValue } from './seasonalityScale'

/** A balance's text: "500" left, "−80" short, "0" empty.
 *
 * The sign goes on the ROUNDED figure, so a few cents short reads "0", not
 * "−0" — a sign on nothing, which read as an overspend too small to show.
 * No "+" on what is left: a balance is not a gain.
 *
 * Masked, every cell reads the mask alone, zero included, so overspending
 * cannot be read off a grid whose cards say a sign-less "$••••". The tint
 * and the "over" weight stay in privacy mode, on purpose: like the Budget
 * page's overspent colour, they show state rather than a figure. */
export function balanceLabel(amount: number, masked: boolean): string {
  if (masked) return PRIVACY_MASK
  const text = abbreviateValue(Math.abs(amount), false)
  if (text === '0') return '0'
  return amount < 0 ? `−${text}` : text
}

/** An Overspent figure's text — what Ready to Assign covered, drawn as the
 * shortfall it was ("−40"), or "—" where it covered nothing. Masked, it is
 * the mask whatever it is: a dash beside masks would say which envelopes
 * went negative, which is what `balanceLabel` keeps zero masked to hide. */
export function overspentLabel(overspent: number, masked: boolean): string {
  if (masked) return PRIVACY_MASK
  return coveredAnything(overspent) ? balanceLabel(-overspent, false) : '—'
}

/** Overspend tint, scaled by how much Ready to Assign covered relative to
 * the worst on screen — colour only where the server says "over". Mixed
 * into the sunken surface rather than transparency, so a sticky totals cell
 * stays opaque while the months scroll under it. */
export function overspendStyle(
  figure: { over: boolean; overspent: number },
  maxOver: number
): CSSProperties {
  if (!figure.over) return {}
  const pct = Math.round(Math.min(1, figure.overspent / maxOver) * 30) + 8
  return {
    background: `color-mix(in srgb, var(--chart-negative) ${pct}%, var(--surface-sunken))`,
  }
}

/** The worst over month on screen, the cells' tint's full scale. The Total
 *  column scales against its own worst (`worstTotalOverspend`): a window's
 *  coverage beside a month's would wash every cell out. */
export function worstOverspend(categories: PlanVsSpentCategory[]): number {
  let worst = 1
  for (const c of categories) {
    for (const m of c.monthly) if (m.over) worst = Math.max(worst, m.overspent)
  }
  return worst
}

export function worstTotalOverspend(categories: PlanVsSpentCategory[]): number {
  let worst = 1
  for (const c of categories) if (c.total.over) worst = Math.max(worst, c.total.overspent)
  return worst
}

/** Whether a totals-row month reads as overspent: any category went over in
 *  a complete month (served `categories_over`). The running month never
 *  does — its spending is still arriving. */
export function monthOverspent(total: PlanVsSpentMonth): boolean {
  return !total.partial_month && total.categories_over > 0
}

/** Whether Ready to Assign covered anything at all, by the cent — the
 *  headline Overspent card's warning. */
export function coveredAnything(overspent: number): boolean {
  return toCents(overspent) > 0
}

/**
 * How a cell's or Total's figures add up, in words — the one wording its
 * tooltip uses, so no one adds the parts on this side:
 * "carried in $400 · spent $100 · left $300".
 *
 * A term that is zero is left out, carryover and spending always said. A
 * span (`covered`) adds what Ready to Assign covered, which is what closes
 * its sum; `other` is named only where the budget page counted something
 * the plan ledger does not.
 */
export function envelopeBreakdown(
  figures: PlanVsSpentFigures & { carried_in: number | null },
  formatMoney: (n: number) => string,
  { span = false }: { span?: boolean } = {}
): string {
  const terms: string[] = [
    figures.carried_in === null
      ? 'carryover unknown'
      : `carried in ${formatMoney(figures.carried_in)}`,
  ]
  if (figures.assigned !== 0) terms.push(`assigned ${formatMoney(figures.assigned)}`)
  if (figures.moved_in !== 0) terms.push(`moved in ${formatMoney(figures.moved_in)}`)
  if (figures.moved_out !== 0) terms.push(`moved out ${formatMoney(figures.moved_out)}`)
  terms.push(`spent ${formatMoney(figures.spent)}`)
  if (toCents(figures.other) !== 0) {
    terms.push(`other ${formatMoney(figures.other)} (pending, starting balance or card refund)`)
  }
  if (span && coveredAnything(figures.overspent)) {
    terms.push(`Ready to Assign covered ${formatMoney(figures.overspent)}`)
  }
  terms.push(`left ${formatMoney(figures.left)}`)
  return terms.join(' · ')
}

export interface PlanVsSpentHeadline {
  chronic: number
  /** The newest COMPLETE month and how many categories went over in it
   *  (served, `categories_over`); null when the window holds none. The
   *  running month is never "last month". */
  lastMonth: { month: string; over: number } | null
  /** The category over most often, the larger coverage breaking a tie. */
  mostOver: { name: string; monthsOver: number; monthsActive: number } | null
}

/** "N chronic · N over in Aug · most over: X" — the question the report
 *  answers, in one line. */
export function planVsSpentHeadline(report: PlanVsSpentReport): PlanVsSpentHeadline {
  const newest = report.month_totals.filter((m) => !m.partial_month).at(-1)
  const overrun = (c: PlanVsSpentCategory) => c.months_over * c.avg_overspend
  const candidates = report.categories.filter((c) => c.months_over > 0)
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

/** The export's wide rows: one per category, what it had left at the end of
 *  each month, then the Total column's figures. */
export function exportRows(categories: PlanVsSpentCategory[]): Record<string, unknown>[] {
  return categories.map((c) => {
    const row: Record<string, unknown> = {
      category: c.category_name,
      group: c.category_group_name,
    }
    for (const cell of c.monthly) row[cell.month.slice(0, 7)] = cell.left
    row.carried_in = c.total.carried_in
    row.total_assigned = c.total.assigned
    row.total_moved_in = c.total.moved_in
    row.total_moved_out = c.total.moved_out
    row.total_funded = c.total.funded
    row.total_spent = c.total.spent
    row.total_other = c.total.other
    row.total_overspent = c.total.overspent
    row.left = c.total.left
    row.months_over = c.months_over
    row.chronic = c.chronic
    return row
  })
}
