import type { NetWorthReport } from '../../../types'

/**
 * The Net Worth report's sentences about figures nobody's ledger adds up.
 * Pure, and takes the page's formatters, so each branch is a one-line test.
 */

type Stated = NetWorthReport['stated_values'][number]
type Stale = NetWorthReport['stale_balances'][number]

function asOf(date: string | null, formatDate: (d: string) => string): string {
  return date ? `as of ${formatDate(date)}` : '(no date recorded)'
}

/**
 * "Assets include $310,000 of stated value — Maple St House as of Sep 2,
 * 2026." A stated value is a claim with a date, and the one that moves net
 * worth up; the footnote named the total and not when any of it was true.
 * Null when there is none of `kind`.
 */
export function statedNote(
  values: Stated[],
  kind: Stated['kind'],
  formatMoney: (n: number) => string,
  formatDate: (d: string) => string
): string | null {
  const mine = values.filter((v) => v.kind === kind)
  if (mine.length === 0) return null
  const total = formatMoney(mine.reduce((sum, v) => sum + v.value, 0))
  const each = mine.map((v) => `${v.name} ${asOf(v.as_of, formatDate)}`).join('; ')
  return kind === 'stated_asset'
    ? `Assets include ${total} of stated value, with no account behind it — ${each}.`
    : `Liabilities include ${total} of debt tracked by hand, with no account behind it — ${each}.`
}

/**
 * The balances in today's net worth that have not moved in the served
 * threshold, oldest first as served: their lines are flat because nothing
 * updated them, not because nothing changed. Null when there are none.
 */
export function staleNote(
  stale: Stale[],
  days: number,
  formatDate: (d: string) => string
): string | null {
  if (stale.length === 0) return null
  const each = stale
    .map(
      (s) =>
        `${s.name} (${s.last_changed ? `last moved ${formatDate(s.last_changed)}` : 'no date recorded'})`
    )
    .join(', ')
  return `Unchanged for ${days}+ days, so flat on the chart because nothing updated ${stale.length === 1 ? 'it' : 'them'}: ${each}.`
}
