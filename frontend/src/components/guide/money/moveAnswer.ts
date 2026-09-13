/**
 * How a served explanation reads. Composition of served facts only — every
 * number and class here arrived in the response.
 */
import type { MoneyFigures, MoveExplanation, ReportFamily } from '../../../api/moneyRules'

export interface FigureLine {
  key: keyof MoneyFigures
  label: string
  value: number
}

const FIGURE_LABEL: [keyof MoneyFigures, string][] = [
  ['income', 'Income'],
  ['spending', 'Spending'],
  ['cost_of_living', 'Cost of living'],
  ['savings', 'Saved'],
  ['debt_principal', 'Debt principal'],
]

/** The report figures a move changes, zeros left out. */
export function figureLines(figures: MoneyFigures): FigureLine[] {
  return FIGURE_LABEL.map(([key, label]) => ({ key, label, value: figures[key] as number })).filter(
    (line) => line.value !== 0
  )
}

/** "Savings rate, Cost of living" from served family keys and served labels. */
export function familyList(
  keys: readonly ReportFamily[],
  families: readonly { key: ReportFamily; label: string }[]
): string {
  const labels = keys.map((k) => families.find((f) => f.key === k)?.label ?? k)
  return labels.join(', ')
}

export function netWorthLine(e: MoveExplanation, formatMoney: (n: number) => string): string {
  if (e.net_worth_delta === 0) return 'Unchanged — the money only moved between your accounts'
  const way = e.net_worth_delta > 0 ? 'Up' : 'Down'
  return `${way} ${formatMoney(Math.abs(e.net_worth_delta))}`
}

/** A figure with its sign spelled out, so "+$1,000 saved" and a withdrawal
 * read differently at a glance. */
export function signedMoney(value: number, formatMoney: (n: number) => string): string {
  return value > 0 ? `+${formatMoney(value)}` : `−${formatMoney(Math.abs(value))}`
}
