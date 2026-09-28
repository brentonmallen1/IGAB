/**
 * How a runway is said — the presentational half of the one runway rule
 * (backend `domain/runway.py`, which does all the arithmetic).
 *
 * "How long does my money last" had four answers on four pages — Days Until
 * Zero, the Burn Rate, the projection, the Emergency Fund's coverage — and none
 * said which question it answered. Now every runway the app shows is the same
 * served figure at a stated choice, and every one of them says that choice in
 * the words below: what a month costs, what money counts, and that the cards
 * were paid first. The Overview card, the projection's headline and pickers,
 * and the Emergency Fund's "Covered" all read this module, so the words cannot
 * drift apart the way the figures did.
 */
import type { RunwayFigure, RunwayMoney, RunwaySpending } from '../types'

/** The spending picker, in order. */
export const RUNWAY_SPENDING_OPTIONS: { value: RunwaySpending; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'cost_of_living', label: 'Cost of living' },
  { value: 'essentials', label: 'Essentials' },
]

/** The money picker, in order. The fund alone is the Emergency Fund report's
 *  question and is never offered here. */
export const RUNWAY_MONEY_OPTIONS: { value: RunwayMoney; label: string }[] = [
  { value: 'checking', label: 'Checking' },
  { value: 'with_fund', label: '+ Emergency fund' },
  { value: 'with_savings', label: '+ Savings accounts' },
]

const SPENDING_WORDS: Record<RunwaySpending, string> = {
  all: 'all spending',
  cost_of_living: 'cost of living',
  essentials: 'Essentials',
}

const MONEY_WORDS: Record<RunwayMoney, string> = {
  checking: 'checking',
  with_fund: 'checking + emergency fund',
  with_savings: 'checking + savings accounts',
  fund: 'emergency fund',
}

/** "Essentials, checking + emergency fund, cards paid" — the choice a runway
 *  was read at. The cards are always named: they are always subtracted. */
export function runwayBasis(figure: Pick<RunwayFigure, 'spending' | 'money'>): string {
  return `${SPENDING_WORDS[figure.spending]}, ${MONEY_WORDS[figure.money]}, cards paid`
}

/** "20.0 months", "1.0 month": one decimal, as served. */
export function runwayMonths(months: number): string {
  return `${months.toFixed(1)} month${months === 1 ? '' : 's'}`
}

export interface RunwayStatement {
  /** The figure, or "—" when there is none to state. */
  value: string
  /** When the money runs out, or why there is no figure. */
  detail: string
  /** The money is already gone: nothing left once the cards are paid. */
  gone: boolean
}

/**
 * What a runway says: its months and the date they run out, or why there is
 * no figure — never a zero standing in for "unknown". `formatDate` is
 * `useFormatters().formatDate`.
 */
export function runwayStatement(
  figure: RunwayFigure,
  formatDate: (day: string) => string
): RunwayStatement {
  if (figure.money_total === null) {
    return { value: '—', detail: 'No emergency fund chosen', gone: false }
  }
  if (figure.monthly_spending === null) {
    return {
      value: '—',
      detail:
        figure.spending === 'essentials'
          ? 'Nothing tagged Essential'
          : 'Nothing tagged Essential or Cost of living',
      gone: false,
    }
  }
  if (figure.months === null) {
    return { value: '—', detail: 'Nothing spent to run out at', gone: false }
  }
  if (figure.money_total <= 0) {
    return { value: runwayMonths(0), detail: 'Nothing left once the cards are paid', gone: true }
  }
  return {
    value: runwayMonths(figure.months),
    detail: figure.runs_out_on ? `to ${formatDate(figure.runs_out_on)}` : '',
    gone: false,
  }
}

/**
 * The Essentials report's fund card, in one line: how long the fund lasts on
 * Essentials with the cards paid ("6.5 months of essentials, cards paid"), or
 * why there is no figure. The same served figure as the Emergency Fund's
 * "Covered", said the same way.
 */
export function fundCoverLine(figure: RunwayFigure): string {
  const said = runwayStatement(figure, () => '')
  if (said.value === '—' || said.gone) return said.detail
  return `${said.value} of essentials, cards paid`
}
