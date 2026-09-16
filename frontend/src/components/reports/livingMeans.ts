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
  /** How far outflows fell under or ran over income, as a whole percentage
   *  of income — see `MeansMargin`. Null with no income to measure against. */
  margin: MeansMargin | null
  /** The "at your means" band as money, in whole cents: outflows from `low`
   *  to `high` inclusive read as at. Null when the standing is unknown. */
  band: { low: number; high: number } | null
}

/**
 * How far outflows sat from income, as a whole percentage of income.
 *
 * **Rounded away from zero, in integer cents.** `pct` is
 * ceil(|income − outflows| × 100 / income), computed on whole cents. The band
 * is inclusive at exactly `AT_MEANS_BAND_PCT` of income, so a figure that is
 * one cent past the band edge must never print as the band's own number: on
 * 5,000 of income, outflows of 4,749.99 read "below" and print 6%, not a 5%
 * that the dialog says is "at". Rounding to nearest would print 5% for both
 * sides of the edge; rounding toward zero would print 5% for a "below" too.
 * Away from zero is the one rounding under which the printed percentage and
 * the verdict can never contradict each other.
 *
 * **Share + margin = 100.** Outflows as a share of income is stated from this
 * figure (`outflowSharePhrase`) rather than rounded separately, so "88% of
 * income" and "12% under income" always add up. A net refund on the outflow
 * side can take the margin past 100 and the share below zero; both are true.
 *
 * `even` only when the two agree to the cent — its `pct` is 0.
 */
export interface MeansMargin {
  pct: number
  direction: 'under' | 'over' | 'even'
}

/** `MeansMargin` from whole cents; null when income is not positive. */
function marginFromCents(incomeCents: number, outflowCents: number): MeansMargin | null {
  if (!(incomeCents > 0)) return null
  const gap = Math.abs(incomeCents - outflowCents)
  // Integer ceil: never a float quotient a hair above an exact integer.
  const whole = Math.floor((gap * 100) / incomeCents)
  const pct = whole * incomeCents < gap * 100 ? whole + 1 : whole
  const direction =
    outflowCents < incomeCents ? 'under' : outflowCents > incomeCents ? 'over' : 'even'
  return { pct, direction }
}

/** The margin as words: "12% under income", "4% over income", "even with
 *  income". */
export function marginPhrase(margin: MeansMargin): string {
  return margin.direction === 'even'
    ? 'even with income'
    : `${margin.pct}% ${margin.direction} income`
}

/** Outflows as a share of income, stated from the margin so the two always
 *  sum to 100: "Outflows were 88% of income". */
export function outflowSharePhrase(margin: MeansMargin): string {
  const share =
    margin.direction === 'under'
      ? 100 - margin.pct
      : margin.direction === 'over'
        ? 100 + margin.pct
        : 100
  return `Outflows were ${share}% of income`
}

/** The card's one line: "$820.00 left over · 12% under income". With no
 *  income, only the net — there is no margin to state. */
export function meansLine(
  income: number,
  outflows: number,
  formatMoney: (amount: number) => string
): string {
  const reading = meansReading(income, outflows)
  const net = netPhrase(reading.net, formatMoney)
  return reading.margin ? `${net} · ${marginPhrase(reading.margin)}` : net
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
  const margin = marginFromCents(incomeCents, outflowCents)

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
      margin: null,
      band: null,
    }
  }

  const tolerance = Math.floor((incomeCents * AT_MEANS_BAND_PCT) / 100)
  const band = { low: (incomeCents - tolerance) / 100, high: (incomeCents + tolerance) / 100 }
  const base = { net, margin, band }

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

/** How many of the newest months the Means trend pools into its headline,
 *  and how many before those it compares against. */
export const MEANS_TREND_POOL_MONTHS = 3

/** One month of income and outflows — the served `MeansMonth`, or an invented
 *  one in an example. */
export interface MeansMonthFigures {
  month: string
  income: number
  outflows: number
}

export interface MeansTrendBar {
  month: string
  income: number
  outflows: number
  /** The month's own reading: its standing, net and margin. */
  reading: MeansReading
  /** The margin signed so that up is good: positive was kept (outflows under
   *  income), negative was short. Null for a month with no income. */
  marginPct: number | null
}

export interface MeansTrend {
  bars: MeansTrendBar[]
  /** The newest `MEANS_TREND_POOL_MONTHS` months pooled — Σincome against
   *  Σoutflows. Unknown when there are no months, or none of them had income. */
  recent: MeansReading
  /** The pool before that, or null when the months do not reach back to it. */
  prior: MeansReading | null
  /** `recent`'s signed margin against `prior`'s, at whole-percent precision.
   *  Null when either has no margin to compare. */
  direction: 'up' | 'down' | 'steady' | null
  /** Months below your means. A month with no income is in neither count's
   *  numerator — it is not a verdict. */
  belowCount: number
  monthsWithIncome: number
}

/** How far a Means trend bar is drawn, either side of zero. A month whose
 *  outflows ran at three times its income would otherwise flatten every other
 *  bar to a sliver; past this the bar stops and the tooltip and table state
 *  the real figure. */
export const MEANS_TREND_CLAMP_PCT = 100

/** A signed margin as drawn: clamped to ±`MEANS_TREND_CLAMP_PCT`. */
export function drawnMargin(marginPct: number): number {
  return Math.max(-MEANS_TREND_CLAMP_PCT, Math.min(MEANS_TREND_CLAMP_PCT, marginPct))
}

/** A margin signed so that up is good: kept is positive, short is negative. */
export function signedMargin(margin: MeansMargin): number {
  return margin.direction === 'over' ? -margin.pct : margin.pct
}

/** Σincome against Σoutflows over some months, read like one period. */
function pooled(months: readonly MeansMonthFigures[]): MeansReading {
  let incomeCents = 0
  let outflowCents = 0
  for (const m of months) {
    incomeCents += toCents(m.income)
    outflowCents += toCents(m.outflows)
  }
  return meansReading(incomeCents / 100, outflowCents / 100)
}

/**
 * The Overview's Means trend, from months oldest first.
 *
 * **Pooled, not averaged.** The headline is the newest three months read as
 * one period — their income summed against their outflows summed — never the
 * mean of three monthly percentages. A month with little income would
 * otherwise swing the average as hard as a month with a full wage: 10% under
 * on 5,000 and 50% over on 500 is a household 5% under on 5,500, not one 20%
 * over. It also means a yearly bill that dips one month is softened by the
 * two around it, which is the point of an average.
 *
 * Every standing is `meansReading`'s, so the ±`AT_MEANS_BAND_PCT` band is the
 * Your Means card's band — written nowhere here.
 */
export function meansTrend(months: readonly MeansMonthFigures[]): MeansTrend {
  const bars = months.map((m) => {
    const reading = meansReading(m.income, m.outflows)
    return {
      month: m.month,
      income: m.income,
      outflows: m.outflows,
      reading,
      marginPct: reading.margin ? signedMargin(reading.margin) : null,
    }
  })
  const cut = Math.max(0, months.length - MEANS_TREND_POOL_MONTHS)
  const recent = pooled(months.slice(cut))
  const priorMonths = months.slice(Math.max(0, cut - MEANS_TREND_POOL_MONTHS), cut)
  const prior = priorMonths.length > 0 ? pooled(priorMonths) : null

  let direction: MeansTrend['direction'] = null
  if (recent.margin && prior?.margin) {
    const now = signedMargin(recent.margin)
    const then = signedMargin(prior.margin)
    direction = now > then ? 'up' : now < then ? 'down' : 'steady'
  }

  return {
    bars,
    recent,
    prior,
    direction,
    belowCount: bars.filter((b) => b.reading.standing === 'below').length,
    monthsWithIncome: bars.filter((b) => b.reading.standing !== 'unknown').length,
  }
}

/** A pooled reading as the Means trend card's value: "Keeping 11%", "Short 4%",
 *  "Even", or an em dash with no income to read. */
export function meansTrendValue(reading: MeansReading): string {
  const { margin } = reading
  if (!margin) return '—'
  if (margin.direction === 'even') return 'Even'
  return margin.direction === 'under' ? `Keeping ${margin.pct}%` : `Short ${margin.pct}%`
}

/** A signed margin as the trend states it beside another: "4%", "−9%". */
export function signedMarginText(margin: MeansMargin): string {
  const signed = signedMargin(margin)
  return signed < 0 ? `−${-signed}%` : `${signed}%`
}

/** The Means trend card's sub line: "3-month average · up from 4%". */
export function meansTrendSub(trend: MeansTrend): string {
  if (trend.monthsWithIncome === 0) return 'Needs a month with income'
  if (!trend.recent.margin) return `No income in the last ${MEANS_TREND_POOL_MONTHS} months`
  const base = `${MEANS_TREND_POOL_MONTHS}-month average`
  if (!trend.direction || !trend.prior?.margin) return base
  if (trend.direction === 'steady') return `${base} · steady`
  return `${base} · ${trend.direction} from ${signedMarginText(trend.prior.margin)}`
}

/** What the strip says to a screen reader: "7 of the last 12 months below your
 *  means". */
export function meansTrendCountPhrase(trend: MeansTrend): string {
  const n = trend.bars.length
  return `${trend.belowCount} of the last ${n} ${n === 1 ? 'month' : 'months'} below your means`
}
