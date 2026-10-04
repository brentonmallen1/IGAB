/** Per-device memory of how many late arrivals were dismissed on a budget's
 *  import month. A convenience: storage can be missing or throw (private
 *  windows, blocked site data), and then the note simply shows. */
const key = (budgetId: string) => `igab.lateArrivals.dismissed.${budgetId}`

export function dismissedCount(budgetId: string): number {
  try {
    const raw = window.localStorage.getItem(key(budgetId))
    const n = raw === null ? 0 : Number(raw)
    return Number.isFinite(n) ? n : 0
  } catch {
    return 0
  }
}

export function rememberDismissed(budgetId: string, count: number): void {
  try {
    window.localStorage.setItem(key(budgetId), String(count))
  } catch {
    // Storage unavailable: the note comes back next visit, which is harmless.
  }
}
