/**
 * What the AI Activity nav item shows, if anything.
 *
 * This lived inline in a header pill — the only badge of its kind up there,
 * next to nothing that explained it, and pointing at a page it did not look
 * like it belonged to. It sits on the nav item now, which is both the thing
 * the count is about and where you go to clear it.
 *
 * The rule is here rather than in either nav so the sidebar and the mobile
 * sheet cannot drift: they render the same three states from one function.
 *
 * - `review` — AI transactions still waiting for you. A number, because a
 *   number is actionable and persists until you deal with it.
 * - `working` — jobs queued or processing and nothing waiting yet. A dot: the
 *   count is transient and the exact figure is not worth reading.
 * - `none` — draw nothing.
 *
 * **A count outranks a spinner.** The header badge had this the other way
 * round, so submitting a second receipt hid the first one's result behind
 * "1 processing". What is waiting for you does not stop waiting because the
 * machine is busy again — and `working` stays true underneath, so the badge
 * still pulses while it is.
 */
export interface AIBadgeState {
  kind: 'none' | 'working' | 'review'
  /** Only meaningful for `review`. */
  count: number
  /** Jobs are in flight — pulse whatever is drawn. */
  working: boolean
}

export function aiBadgeState({
  active,
  needsReview,
}: {
  active: number
  needsReview: number
}): AIBadgeState {
  const working = active > 0
  if (needsReview > 0) return { kind: 'review', count: needsReview, working }
  if (working) return { kind: 'working', count: 0, working }
  return { kind: 'none', count: 0, working: false }
}

/** What the badge means, for a tooltip and for a screen reader. */
export function aiBadgeLabel(state: AIBadgeState): string {
  if (state.kind === 'review') {
    const plural = state.count === 1 ? 'transaction' : 'transactions'
    const waiting = `${state.count} AI ${plural} to approve`
    return state.working ? `${waiting} — more still processing` : waiting
  }
  if (state.kind === 'working') return 'AI is processing'
  return ''
}
