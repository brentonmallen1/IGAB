import { parseAmountExpressionInput } from '../../../utils/amountExpression'
import { toCents } from '../../../utils/money'

/**
 * What the editor's two amount boxes add up to, and whether they add up at
 * all.
 *
 * The editor derives its amount in four places — the save, the split
 * remainder, the similar-transactions lookup and the AI category hint — and
 * each spelled it out again as `parseAmountExpressionInput(x) || 0`. That
 * `|| 0` did two jobs at once, which is what made it wrong:
 *
 * - **A blank box is zero**, and one of the two boxes is always blank. That
 *   part has to stay.
 * - **Unparseable text became zero too.** The parser returns NaN for text
 *   that is not an amount ("4l.80", "1,2,3", a bare "-5", an expression that
 *   never evaluated), and the editor's Save was never gated on the amount —
 *   so a mistyped digit on an existing row saved $0.00 over it without a
 *   word. CLAUDE.md bans `|| 0` on a parsed amount for exactly this.
 *
 * Null is the difference: nothing typed here is an amount. The save refuses
 * it; the read-only consumers treat it as "no amount yet", which is what it
 * is while someone is still typing.
 *
 * Zero itself is a real answer and stays one: the receipt worker files a $0
 * stub when a scan exhausts its retries, and reviewing that stub to fix its
 * payee must not be blocked by its own amount.
 */
export interface EditorAmount {
  /** Signed integer cents — negative for an outflow. */
  cents: number
  /** The same figure in dollars, as the save and the API want it. */
  dollars: number
}

/**
 * The amount as typed, or null when one of the boxes holds something that is
 * not an amount.
 *
 * Outflow wins when it holds anything above zero, which is the same choice
 * the save has always made: `outflow || inflow` picked the string "0" over a
 * real inflow, so the editor checked one number and wrote another.
 */
export function editorAmount(outflow: string, inflow: string): EditorAmount | null {
  const out = boxCents(outflow)
  const inn = boxCents(inflow)
  if (out === null || inn === null) return null
  const cents = out > 0 ? -out : inn
  return { cents, dollars: cents / 100 }
}

/** One box: blank is zero, unparseable is null. */
function boxCents(value: string): number | null {
  if (value.trim() === '') return 0
  const dollars = parseAmountExpressionInput(value)
  if (Number.isNaN(dollars)) return null
  return toCents(dollars)
}
