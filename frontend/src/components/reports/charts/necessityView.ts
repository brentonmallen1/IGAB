/**
 * How the two necessity tiers read as a standing, and nothing more.
 *
 * The server decides what the tiers CONTAIN — that is a rule about rows, and
 * it lives in `domain.activity_class.tier_scope`. What a ratio MEANS for a
 * household is pure presentational composition of figures the server already
 * sent, and the client is missing no input, so by the boundary rule it belongs
 * here in one module rather than in a second server field.
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

/** What share of committed spending a lean month could shed, 0-100.
 *
 * Null rather than zero when nothing is committed: a share of nothing is
 * unknown, and rendering 0% would read as "nothing is sheddable". Null too
 * when the gap itself is unknown — nothing tagged Essential.
 */
export function sheddableShare(costOfLiving: number, nonEssential: number | null): number | null {
  return nonEssential === null ? null : shareOfTotal(nonEssential, costOfLiving)
}
