/**
 * How the two necessity tiers read as a standing, and nothing more.
 *
 * The server decides what the tiers CONTAIN — that is a rule about rows, and
 * it lives in `domain.activity_class.tier_scope`. It serves three figures:
 * the wide tier, the lean one and take-home. Everything the page makes of
 * those — the gap between the tiers, each ratio, and what a ratio MEANS for a
 * household — is pure presentational composition of figures the server already
 * sent, and the client is missing no input, so by the boundary rule it belongs
 * here in one module rather than in a server field no backend path reads.
 *
 * The bands lean on the 50/30/20 rule of thumb — roughly half of take-home to
 * needs, a third to wants, a fifth saved — because inventing thresholds and
 * then rendering them as a verdict would be dressing a guess as advice. They
 * are deliberately coarse, and the copy says "rule of thumb" out loud.
 */
import { shareOfTotal } from '../drillDownTotals'

/** Ordered worst-to-best so a caller can compare standings. */
export type NecessityStanding = 'no-headroom' | 'tight' | 'workable' | 'comfortable' | 'unknown'

export interface NecessityReading {
  standing: NecessityStanding
  /** One sentence, stating the fact rather than prescribing an action. */
  note: string
  /** True when the lean tier alone exceeds take-home. A different and worse
   *  fact than a high required ratio, so it is called out separately. */
  underwater: boolean
}

/**
 * The standing, from the wide ratio and the lean one.
 *
 * `requiredRatio` is cost of living as a percentage of take-home;
 * `essentialsRatio` is the same for essentials. Both are null when no income
 * is on record — a ratio against zero is unknown, not 100%.
 */
export function necessityReading(
  requiredRatio: number | null,
  essentialsRatio: number | null
): NecessityReading {
  if (requiredRatio === null) {
    return {
      standing: 'unknown',
      note: 'No income recorded in this window, so there is nothing to measure these against.',
      underwater: false,
    }
  }

  // Checked before the bands: a household whose essentials alone outrun its
  // take-home is in a different situation from one merely short of headroom,
  // and saying "no headroom" would understate it.
  const underwater = essentialsRatio !== null && essentialsRatio > 100
  if (underwater) {
    return {
      standing: 'no-headroom',
      note: 'What you could not cut costs more than you take home. The gap below is not enough to close it.',
      underwater: true,
    }
  }

  if (requiredRatio > 90) {
    return {
      standing: 'no-headroom',
      note: 'Almost everything you take home is already committed, so an unplanned bill has nowhere to come from.',
      underwater: false,
    }
  }
  if (requiredRatio > 70) {
    return {
      standing: 'tight',
      note: 'Most of your take-home is committed. There is room, but not much of it.',
      underwater: false,
    }
  }
  if (requiredRatio > 50) {
    return {
      standing: 'workable',
      note: 'Committed spending is over half your take-home — around where the 50/30/20 rule of thumb puts it.',
      underwater: false,
    }
  }
  return {
    standing: 'comfortable',
    note: 'Committed spending is no more than half your take-home, which leaves room for the rest.',
    underwater: false,
  }
}

/**
 * Cost of living less essentials: what a lean month could shed.
 *
 * Null whenever essentials is — nothing tagged Essential means the wide tier
 * is every category, and the difference would not be a gap.
 *
 * Floored at zero: the wide tier contains the lean one, but its tag arms net
 * refunds, so a refund filed to a Cost-of-living category can push the
 * difference below zero, and nobody committed to a negative amount.
 *
 * Composed here rather than served. It is arithmetic on two figures the server
 * already sends, no backend path read the served copy, and the sheddable share
 * of the same shape was already on this side — so by the boundary rule the
 * whole family lives here.
 */
export function nonEssentialSpend(costOfLiving: number, essentials: number | null): number | null {
  return essentials === null ? null : Math.max(costOfLiving - essentials, 0)
}

/**
 * One tier figure as a percentage of another, 0-100 — the report's only ratio
 * rule, asked three times: cost of living against take-home ("Required"),
 * essentials against take-home (what `necessityReading` bands), and the gap
 * against cost of living (what a lean month could shed).
 *
 * Null rather than zero when the part is unknown — nothing tagged Essential —
 * or when the whole is not positive, no income on record: a share of nothing,
 * or of an unknown, is unknown, and 0% would read as a fact.
 *
 * **It divides the SERVED, cent-rounded averages the cards print**, not the
 * window totals behind them, because a ratio quoted beside two cards has to be
 * their quotient: a reader checking $1,800 against $3,600 must land on the 50%
 * the page shows. The server's copy divided the unrounded totals, which can
 * differ in the hundredths.
 */
export function necessityShare(part: number | null, whole: number): number | null {
  return part === null ? null : shareOfTotal(part, whole)
}
