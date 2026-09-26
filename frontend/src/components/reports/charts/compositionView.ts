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
 * the window is left out of the chart and its legend.
 *
 * The palette has eight slots (`paletteSize`), and a budget with seven account types
 * has nine bands: the ninth wrapped onto the first, and "Debts tracked by
 * hand" drew in Checking's colour beside it. So a drawn band whose slot an
 * earlier drawn band holds moves to the next free one — which only ever
 * happens past the palette's size, so below it every slot is the list's.
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

export function compositionBands(
  report: AccountCompositionReport,
  paletteSize: number
): CompositionBand[] {
  const keys = [...report.series, STATED_BAND, MANUAL_DEBT_BAND]
  const valuesOf = (key: string) =>
    report.points.map((p) =>
      key === STATED_BAND
        ? p.stated_assets
        : key === MANUAL_DEBT_BAND
          ? p.manual_debts
          : (p.balances[key] ?? 0)
    )
  const taken = new Set<number>()
  const bands: CompositionBand[] = []
  keys.forEach((key, place) => {
    const values = valuesOf(key)
    if (!values.some((v) => v !== 0)) return
    let slot = place % paletteSize
    // Past the palette's size: the next slot no drawn band holds, if any.
    for (let step = 0; step < paletteSize && taken.has(slot); step++) {
      slot = (slot + 1) % paletteSize
    }
    taken.add(slot)
    bands.push({ key, colorSlot: slot, values })
  })
  return bands
}

/**
 * What the chart plots for a band at point `i`: its value, except a zero in a
 * band that only ever sits below the axis, which is left out (null).
 *
 * The sign offset stacks a zero on the positive side. A debt band empty in
 * August and owing in September was drawn from the top of the assets in
 * August down past the axis in September: a sliver across the whole chart
 * that read as a balance swinging through zero. Left out, the band starts
 * where it has something to draw.
 */
export function plotted(band: CompositionBand, i: number): number | null {
  const value = band.values[i]
  return value === 0 && band.values.every((v) => v <= 0) ? null : value
}

/** The label a band is drawn and listed under. */
export function bandLabel(key: string, typeLabel: (key: string) => string): string {
  if (key === STATED_BAND) return 'Stated values'
  if (key === MANUAL_DEBT_BAND) return 'Debts tracked by hand'
  return typeLabel(key)
}
