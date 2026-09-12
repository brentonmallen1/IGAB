/**
 * Whether a period was lived above, at or below its means — the verdict, and
 * nothing more.
 *
 * The definition, decided by the user: over the Overview's own date range,
 * compare income with everything living cost, where **outflows = spending +
 * debt payments**. Money moved into savings is not an outflow; it is what was
 * left over.
 *
 * The server decides what an outflow CONTAINS — that is a rule about rows, and
 * it lives in `COST_OF_LIVING_CLASSES` — and serves the total as
 * `outflows_this_month`. What the page makes of income against that figure is
 * pure presentational composition of two served facts, and no backend path
 * decides it, so by the boundary rule it lives here, once. The Overview's card
 * and its dialog both read this module; the band is written nowhere else.
 */
import { toCents } from '../../utils/money'
import { shareOfTotal } from './drillDownTotals'

/** Outflows within this percentage of income, either side, read as "at your
 *  means". Deliberately coarse: a few dollars either way on a month is noise,
 *  not a change in how a household is living. */
export const AT_MEANS_BAND_PCT = 5

export type MeansStanding = 'below' | 'at' | 'above' | 'unknown'

export interface MeansReading {
  standing: MeansStanding
  /** The whole verdict as a phrase: "Living below your means". */
  label: string
  /** The card's one-word value: "Below". An em dash when unknown. */
  short: string
  /** One sentence, stating the fact rather than prescribing an action. */
  note: string
  /** Income less outflows, to the cent: positive was left over, negative was
   *  short. Stated even when the standing is unknown — it is still a fact. */
  net: number
  /** Outflows as a percentage of income, or null with no income to be a
   *  share of. */
  outflowShare: number | null
  /** The "at your means" band as money, in whole cents: outflows from `low`
   *  to `high` inclusive read as at. Null when the standing is unknown. */
  band: { low: number; high: number } | null
}

/** The net as words — "$820.00 left over", "$300.00 short" — for the card and
 *  the dialog alike. Takes the page's formatter so privacy mode masks it. */
export function netPhrase(net: number, formatMoney: (amount: number) => string): string {
  return net < 0 ? `${formatMoney(-net)} short` : `${formatMoney(net)} left over`
}

/**
 * The standing, from the period's income and its outflows.
 *
 * **Read in whole cents.** The band's half-width is `AT_MEANS_BAND_PCT` of
 * income, floored to a cent, so the band a reader is shown IS the rule: a
 * figure printed as the band's top edge is inside it, and one cent more is
 * not. Comparing unrounded floats would let $105.105 of band say "at" to a
 * $105.11 the dialog prints as outside it.
 *
 * **Unknown when income is not positive.** No income means nothing to measure
 * against, and a negative income — a period whose clawbacks beat what came in
 * — is no better a yardstick. Neither is a verdict, whatever went out.
 */
export function meansReading(income: number, outflows: number): MeansReading {
  const incomeCents = toCents(income)
  const outflowCents = toCents(outflows)
  const net = (incomeCents - outflowCents) / 100
  const outflowShare = shareOfTotal(outflowCents, incomeCents)

  if (!(incomeCents > 0)) {
    return {
      standing: 'unknown',
      label: 'No income this period',
      short: '—',
      note:
        incomeCents < 0
          ? 'Income for this period nets below zero — more was taken back than came in — so there is nothing to measure outflows against.'
          : 'No income was recorded in this period, so there is nothing to measure outflows against.',
      net,
      outflowShare: null,
      band: null,
    }
  }

  const tolerance = Math.floor((incomeCents * AT_MEANS_BAND_PCT) / 100)
  const band = { low: (incomeCents - tolerance) / 100, high: (incomeCents + tolerance) / 100 }
  const base = { net, outflowShare, band }

  if (outflowCents > incomeCents + tolerance) {
    return {
      ...base,
      standing: 'above',
      label: 'Living above your means',
      short: 'Above',
      note: 'More went out on living than came in. The difference came from somewhere else — cash on hand, savings or credit.',
    }
  }
  if (outflowCents >= incomeCents - tolerance) {
    return {
      ...base,
      standing: 'at',
      label: 'Living at your means',
      short: 'At',
      note: `What went out on living was within ${AT_MEANS_BAND_PCT}% of what came in, either side — close to breaking even.`,
    }
  }
  return {
    ...base,
    standing: 'below',
    label: 'Living below your means',
    short: 'Below',
    note: 'Less went out on living than came in. The difference was left over.',
  }
}
