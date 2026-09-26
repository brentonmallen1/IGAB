/**
 * The recharts props for a stack whose segments can be negative. Spread it on
 * the chart (`<BarChart {...MIXED_SIGN_STACK}>`), never spell the offset.
 *
 * recharts' default offset ("none") stacks each segment from the top of the one
 * below it whatever its sign, so a negative segment is drawn downwards from
 * there: it paints over its neighbour, and a positive segment above it starts
 * below zero. "sign" stacks positives up from the axis and negatives down from
 * it, where each reads as what it is. With every segment positive the two
 * offsets draw the same bars, so a chart whose figures only might go negative
 * loses nothing by taking it.
 *
 * Three charts wrote `stackOffset="sign"` inline, each with its own comment,
 * and a fourth did not: Savings Rate stacks Saved under Debt Paid, and a month
 * that drew money back out of savings (a negative Saved) drew a positive debt
 * payment below zero. A rule every stacked chart needs is one constant.
 */
export const MIXED_SIGN_STACK = { stackOffset: 'sign' } as const
