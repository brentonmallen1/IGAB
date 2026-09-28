/**
 * Which way a metric card's change should go to be good news, and the tone
 * that makes it. Pure, beside `MetricCard`, which draws it.
 *
 * The card coloured a delta by its sign, so "Spent +21%" was green: more
 * spending drawn in the colour of a gain. The sign says which way a figure
 * moved; only the figure knows which way is good, so every delta says.
 */

/** `up` for a figure that is better higher (net worth), `down` for one that
 *  is better lower (spending), `neutral` where a change is neither. */
export type GoodDirection = 'up' | 'down' | 'neutral'

export type DeltaTone = 'good' | 'bad' | 'neutral'

/** The tone of a percentage change. A change that prints as 0.0% is neutral
 *  whichever way it rounded from. */
export function deltaTone(pct: number, good: GoodDirection): DeltaTone {
  // `toFixed(1)` is what the card prints, so "no change" is what reads as one.
  if (good === 'neutral' || Number(pct.toFixed(1)) === 0) return 'neutral'
  return pct > 0 === (good === 'up') ? 'good' : 'bad'
}
