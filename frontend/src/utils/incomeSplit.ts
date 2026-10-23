import type { IncomeSplitLine, IncomeSplitReport } from '../types'

/**
 * Income Split as the page draws it: the 50/30/20 rule, each bucket's share
 * of take-home, and how far it sits from the rule.
 *
 * The server serves money only (services/income_split.py) — which rows are
 * needs, wants or savings is its rule, because it decides it. The rule of
 * thumb is not: no backend path reads a 50 or a 30, so the figures and the
 * words for comparing against them live here, once, for both places that
 * draw the split (the report and the Guide's roadmap node).
 */

/** The rule of thumb, in percent of take-home. */
export const RULE = { needs: 50, wants: 30, savings: 20 } as const

/** Where the rule's boundaries fall on the bar: needs end at 50, wants at 80. */
export const RULE_TICKS = [RULE.needs, RULE.needs + RULE.wants] as const

/** At or above this share of take-home unfiled, the split can move a lot once
 *  it is filed: the page dims the ticks and stops stating gaps. */
export const UNFILED_WARN_PCT = 25

export type BucketKey = 'needs' | 'wants' | 'savings' | 'uncategorized' | 'left'

export const BUCKET_LABEL: Record<BucketKey, string> = {
  needs: 'Needs',
  wants: 'Wants',
  savings: 'Savings & debt',
  uncategorized: 'Uncategorized',
  left: 'Left over',
}

/** Each bucket's money, in bar order. */
export function bucketAmounts(r: IncomeSplitReport): Record<BucketKey, number> {
  return {
    needs: r.needs.total,
    wants: r.wants.total,
    savings: r.savings_debt.total,
    uncategorized: r.uncategorized.total,
    left: r.left_over,
  }
}

const ORDER: BucketKey[] = ['needs', 'wants', 'savings', 'uncategorized', 'left']

/**
 * Whole-percent shares of take-home that add up to 100 — largest remainder,
 * so "58% · 24% · 12% · 2% · 4%" never reads 99 or 101. Null with no income
 * to take a share of.
 *
 * When outflows ran past income, Left over is negative and the positive
 * buckets are each rounded on their own: they rightly sum past 100.
 */
export function shares(r: IncomeSplitReport): Record<BucketKey, number> | null {
  if (!(r.income > 0)) return null
  const amounts = bucketAmounts(r)
  const raw = ORDER.map((k) => (amounts[k] / r.income) * 100)
  if (amounts.left < 0 || raw.some((x) => x < 0)) {
    return Object.fromEntries(ORDER.map((k, i) => [k, Math.round(raw[i])])) as Record<
      BucketKey,
      number
    >
  }
  const floors = raw.map(Math.floor)
  let short = 100 - floors.reduce((a, b) => a + b, 0)
  const byRemainder = raw
    .map((x, i) => ({ i, rem: x - Math.floor(x) }))
    .sort((a, b) => b.rem - a.rem)
  for (const { i } of byRemainder) {
    if (short <= 0) break
    floors[i] += 1
    short -= 1
  }
  return Object.fromEntries(ORDER.map((k, i) => [k, floors[i]])) as Record<BucketKey, number>
}

/** "8 pts over", "6 pts under", "on the rule" — a distance, never a verdict:
 *  where a household lives decides a lot of the needs figure. */
export function gapPhrase(sharePct: number, rulePct: number): string {
  const gap = sharePct - rulePct
  if (gap === 0) return 'on the rule'
  return `${Math.abs(gap)} pt${Math.abs(gap) === 1 ? '' : 's'} ${gap > 0 ? 'over' : 'under'}`
}

/** The rule's figure for a bucket, or null for the two it says nothing about. */
export function ruleFor(key: BucketKey): number | null {
  if (key === 'needs') return RULE.needs
  if (key === 'wants') return RULE.wants
  if (key === 'savings') return RULE.savings
  return null
}

export interface BarSegment {
  key: BucketKey | 'committed'
  /** Width as a percent of the bar. */
  width: number
}

export interface BarGeometry {
  segments: BarSegment[]
  /** Where take-home ends, as a percent of the bar: 100 unless outflows ran
   *  past it, when the bar runs on and this marks the line it crossed. */
  incomeAt: number
  /** The rule's 50 and 80, as percents of the bar. */
  ticks: number[]
  /** Outflows past take-home, as money; 0 when there is none. */
  over: number
}

/**
 * The bar: one segment per bucket, the committed part of Wants drawn as its
 * own darker segment first. Scaled to take-home, or to the outflows when
 * they ran past it, so overspending runs past the income line instead of
 * squeezing everything to fit.
 */
export function barGeometry(r: IncomeSplitReport): BarGeometry | null {
  if (!(r.income > 0)) return null
  const a = bucketAmounts(r)
  const committed = Math.max(0, sum(r.wants.committed))
  const chosen = Math.max(0, a.wants - committed)
  const outflows =
    Math.max(0, a.needs) +
    committed +
    chosen +
    Math.max(0, a.savings) +
    Math.max(0, a.uncategorized)
  const scale = Math.max(r.income, outflows)
  const pct = (x: number) => (Math.max(0, x) / scale) * 100
  return {
    segments: [
      { key: 'needs', width: pct(a.needs) },
      { key: 'committed', width: pct(committed) },
      { key: 'wants', width: pct(chosen) },
      { key: 'savings', width: pct(a.savings) },
      { key: 'uncategorized', width: pct(a.uncategorized) },
      { key: 'left', width: pct(a.left) },
    ],
    incomeAt: (r.income / scale) * 100,
    ticks: RULE_TICKS.map((t) => (t / 100) * (r.income / scale) * 100),
    over: Math.max(0, outflows - r.income),
  }
}

/** The unfiled share is high enough that the split is not yet a reading. */
export function tooUnfiled(r: IncomeSplitReport): boolean {
  return r.income > 0 && (r.uncategorized.total / r.income) * 100 >= UNFILED_WARN_PCT
}

export function sum(lines: IncomeSplitLine[]): number {
  return lines.reduce((acc, line) => acc + line.total, 0)
}

/** The "Counted because" chip. */
export const REASON_LABEL: Record<IncomeSplitLine['reason'], string> = {
  essential: 'Essential',
  essential_debt: 'Essential · debt payment',
  cost_of_living: 'Cost of living',
  untagged: 'No tag',
  debt_not_essential: 'Debt payment · not Essential',
  debt_no_category: 'Debt payment · no category',
  saved: 'Saved',
}

/** A saved line carries the Savings Rate's own reading ("held in a Savings
 *  envelope"); every other line its reason. */
export function reasonChip(line: IncomeSplitLine): string {
  return line.reason === 'saved' && line.note ? `Saved · ${line.note}` : REASON_LABEL[line.reason]
}

/** The second line under a row's name, or null: the spread bill, the debt
 *  against its minimum. `money` is the page's formatter. */
export function lineDetail(line: IncomeSplitLine, money: (n: number) => string): string | null {
  if (line.spread && line.as_paid !== null) {
    return `${money(line.as_paid)} paid in this range, spread over 12 months`
  }
  if (line.minimum !== null) {
    const above = line.above_minimum ?? 0
    return above > 0
      ? `Minimum ${money(line.minimum)} a month today — ${money(above)} paid above it`
      : `Minimum ${money(line.minimum)} a month today`
  }
  if (line.minimum_unknown) return 'No minimum payment on file'
  return null
}

/** Whether to state figures per month (a whole number of months, more than
 *  one) or as the range's total. */
export function perMonthDivisor(r: IncomeSplitReport): number {
  return r.whole_months && r.months > 1 ? r.months : 1
}
