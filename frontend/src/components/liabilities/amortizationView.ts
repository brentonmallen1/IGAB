/** Pure view math for the amortization schedule — year grouping and totals,
 * extracted so a 360-row mortgage is testable without mounting a table. */

import type { AmortizationMonth } from '../../api/liabilities'

export interface AmortizationYear {
  year: number
  months: AmortizationMonth[]
  /** Sums over the year's months; balance is the year's last month's. */
  payments: number
  principal: number
  interest: number
  endBalance: number
}

/**
 * One row per calendar year, months beneath — the classic presentation, and
 * the difference between reading a 30-year mortgage whole and clicking
 * "show more" fifteen times to reach the end.
 */
export function groupByYear(schedule: AmortizationMonth[]): AmortizationYear[] {
  const years: AmortizationYear[] = []
  for (const m of schedule) {
    const year = Number(m.date.slice(0, 4))
    let bucket = years[years.length - 1]
    if (!bucket || bucket.year !== year) {
      bucket = { year, months: [], payments: 0, principal: 0, interest: 0, endBalance: 0 }
      years.push(bucket)
    }
    bucket.months.push(m)
    bucket.payments += m.payment
    bucket.principal += m.principal_paid
    bucket.interest += m.interest_paid
    bucket.endBalance = m.balance
  }
  return years
}

/** Whole-schedule totals for the footer. `principal` equals the starting
 *  balance exactly whenever the schedule pays off — the engine's own pinned
 *  invariant, restated where the reader can check it. */
export function scheduleTotals(schedule: AmortizationMonth[]): {
  payments: number
  principal: number
  interest: number
} {
  return schedule.reduce(
    (acc, m) => ({
      payments: acc.payments + m.payment,
      principal: acc.principal + m.principal_paid,
      interest: acc.interest + m.interest_paid,
    }),
    { payments: 0, principal: 0, interest: 0 }
  )
}
