import type { TrackingEntry } from '../types'

/**
 * What the balance charts say about the months something began being counted.
 *
 * The server decides what arrived and when (`domain/tracking_start.py`: an
 * account's opening rows, a stated value's or manual debt's first point) and
 * places each arrival on the point whose month holds it. This module only
 * words it — one sentence per marked month, shared by Net Worth, Account
 * Composition, Liabilities and Savings, so the same arrival reads the same on
 * every chart it moves.
 *
 * Pure, and takes the page's formatters, so each branch is a one-line test.
 */

export interface ArrivalMark {
  /** Index of the chart point the arrival sits on. */
  index: number
  /** That point's date, as served. */
  date: string
  /** The marker's label on the chart: its order among the marks, from 1. */
  label: string
  /** "2 accounts added: +$17,700", for the list under the chart. */
  summary: string
  entries: TrackingEntry[]
}

const NOUNS: Record<TrackingEntry['kind'], [string, string, string]> = {
  account: ['account', 'accounts', 'added'],
  stated_asset: ['value', 'values', 'first stated'],
  manual_debt: ['debt', 'debts', 'first recorded'],
}

const KIND_ORDER: TrackingEntry['kind'][] = ['account', 'stated_asset', 'manual_debt']

/** "2 accounts added · 1 value first stated: +$317,700". The total carries
 *  its sign whichever way it points: a card arriving owing is a minus on net
 *  worth, and says so. */
export function arrivalSummary(
  entries: TrackingEntry[],
  formatMoney: (n: number) => string
): string {
  const parts = KIND_ORDER.flatMap((kind) => {
    const count = entries.filter((e) => e.kind === kind).length
    if (count === 0) return []
    const [one, many, verb] = NOUNS[kind]
    return [`${count} ${count === 1 ? one : many} ${verb}`]
  })
  const total = entries.reduce((sum, e) => sum + e.amount, 0)
  return `${parts.join(' · ')}: ${signedMoney(total, formatMoney)}`
}

/** "Maple St House +$300,000" — one arrival, for a tooltip or a list. */
export function arrivalLine(entry: TrackingEntry, formatMoney: (n: number) => string): string {
  return `${entry.name} ${signedMoney(entry.amount, formatMoney)}`
}

/** "+$1,200" / "−$1,200": an explicit sign, since an arrival can go either way. */
export function signedMoney(amount: number, formatMoney: (n: number) => string): string {
  if (amount === 0) return formatMoney(0)
  return `${amount > 0 ? '+' : '−'}${formatMoney(Math.abs(amount))}`
}

/** Every point that carries an arrival, numbered in chart order. */
export function arrivalMarks(
  points: { date: string; entries: TrackingEntry[] }[],
  formatMoney: (n: number) => string
): ArrivalMark[] {
  return points
    .map((p, index) => ({ p, index }))
    .filter(({ p }) => p.entries.length > 0)
    .map(({ p, index }, order) => ({
      index,
      date: p.date,
      label: String(order + 1),
      summary: arrivalSummary(p.entries, formatMoney),
      entries: p.entries,
    }))
}

/**
 * The headline change and what it leaves out, or null with no change to state.
 *
 * `likeForLike` is the served change less what arrived after the first point;
 * `entered` is that arrival total and `drawn` the change as the chart draws
 * it. "−$3,400 like-for-like" alone would hide why the chart climbs by $620k,
 * so the gap is named beside it when there is one.
 */
export function likeForLikeLine(
  likeForLike: number | null,
  entered: number,
  drawn: number,
  formatMoney: (n: number) => string
): { value: string; sub: string } | null {
  if (likeForLike === null) return null
  return {
    value: signedMoney(likeForLike, formatMoney),
    sub:
      entered === 0
        ? 'Nothing began being counted in this range'
        : `${signedMoney(drawn, formatMoney)} drawn, less ${signedMoney(entered, formatMoney)} from tracking starting`,
  }
}

/** The first month a series has a figure, or null when it has none — the
 *  month "set aside starts" on a chart that is blank before it. */
export function firstFigure(values: (number | null)[]): number | null {
  const index = values.findIndex((v) => v !== null)
  return index === -1 ? null : index
}
