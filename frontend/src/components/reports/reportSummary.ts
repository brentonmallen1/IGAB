/** Two rules for a report's pinned header (`ReportHeader`, `MetricRow`),
 * pure so each branch is a one-line test. */

/** Whether the value boxes are summarised in the pinned header: once the row
 *  has scrolled up under the header's bottom edge, and not before.
 *
 *  The boxes stay where they are and the header shows a one-line copy.
 *  Shrinking the boxes themselves was the obvious version and loops: the
 *  page gets shorter, the scroll position moves, the header lets go, the
 *  boxes grow back. The copy hangs under the header out of flow, so the
 *  page's height never changes. A row still below the fold is never
 *  summarised — its bottom is below the header's, not above. */
export function summaryShown(rowBottom: number, headerBottom: number | null): boolean {
  return headerBottom !== null && rowBottom <= headerBottom
}

/** How much of a header scrolls away before it pins: everything above its
 *  last row, which holds the controls. On a wide screen the header is one
 *  row and nothing does; on a phone the title and subtitle stack above the
 *  controls — the report is already named in the chrome above — and only
 *  the controls stay.
 *
 *  Offsets inside the header: `lastTop` is the last child's top, `firstTop`
 *  and `firstBottom` the first child's (the title's). The controls count as
 *  a row of their own only when they start below the title; beside it,
 *  centring drops them a pixel or two, which is not a row to scroll away. */
export function pinnedLead(lastTop: number, firstTop: number, firstBottom: number): number {
  if (lastTop < firstBottom) return 0
  return Math.max(0, Math.round(lastTop - firstTop))
}

/** The most of the reports pane a pinned header may cover. Past it the
 *  header does not pin at all and scrolls away as it always did: on a phone
 *  Liabilities' seven type filters, range, log scale and export wrap to four
 *  rows, and pinned they took a fifth of the screen from the debts beneath.
 *  Every other report pins an eighth or less. */
export const MAX_PINNED_SHARE = 0.15

/** Whether a header whose pinned part is `pinned` px tall may pin in a pane
 *  `paneHeight` px tall. A pane not yet measured (0) does not forbid it. */
export function mayPin(pinned: number, paneHeight: number): boolean {
  return paneHeight <= 0 || pinned <= paneHeight * MAX_PINNED_SHARE
}
