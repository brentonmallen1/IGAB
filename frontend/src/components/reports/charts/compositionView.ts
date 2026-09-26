import type { AccountCompositionReport } from '../../../types'

/**
 * The bands Account Composition stacks, each with a colour that holds.
 *
 * Every account type the budget has, in the served order
 * (`account_composition`'s `series`: the registry's), then the two bands no
 * account holds — stated values above zero, debts tracked by hand below — so
 * the stack sums to the Net line. It floated above the stack by a house's
 * worth with a footnote saying so.
 *
 * A band's colour slot is its place in that full list, not among the bands
 * drawn: colours were assigned over the types that had a row in the window,
 * sorted, so a range that dropped one repainted every type after it and
 * "Checking" was a different colour on each range. A band that is zero across
 * the window is left out of the chart and its legend but keeps its slot.
 */

export const STATED_BAND = 'stated_assets'
export const MANUAL_DEBT_BAND = 'manual_debts'

export interface CompositionBand {
  /** The account-type key, or one of the two band keys above. */
  key: string
  /** Index into the chart palette (`chartColor`). */
  colorSlot: number
  /** One figure per point, signed: debts below zero. */
  values: number[]
}

export function compositionBands(report: AccountCompositionReport): CompositionBand[] {
  const typed = report.series.map((key, slot) => ({
    key,
    colorSlot: slot,
    values: report.points.map((p) => p.balances[key] ?? 0),
  }))
  const n = report.series.length
  return [
    ...typed,
    { key: STATED_BAND, colorSlot: n, values: report.points.map((p) => p.stated_assets) },
    { key: MANUAL_DEBT_BAND, colorSlot: n + 1, values: report.points.map((p) => p.manual_debts) },
  ].filter((band) => band.values.some((v) => v !== 0))
}

/** The label a band is drawn and listed under. */
export function bandLabel(key: string, typeLabel: (key: string) => string): string {
  if (key === STATED_BAND) return 'Stated values'
  if (key === MANUAL_DEBT_BAND) return 'Debts tracked by hand'
  return typeLabel(key)
}
