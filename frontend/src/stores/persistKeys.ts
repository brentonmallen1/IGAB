/** Every localStorage key a zustand `persist` store writes.
 *
 * Declared in one place so the crash-recovery escape hatch cannot fall behind
 * the stores: ErrorBoundary cleared two of the three, so a render crash driven
 * by persisted appStore state (a stale currentBudgetId, a selectedMonth a
 * chart chokes on) survived "Reset saved view & reload" and the user stayed
 * stuck — the exact incident the boundary exists to end.
 *
 * Each store passes its own entry to `persist({ name })`, so a new store that
 * forgets to add itself here is a compile error at that call site rather than
 * a silent gap.
 */
export const PERSIST_KEYS = {
  app: 'igab-app',
  ui: 'igab-ui',
  reports: 'igab-reports',
} as const

/** Keys safe to clear when recovering from a render crash. All of them: each
 *  holds view state the app rebuilds from the server, never user data. */
export const RECOVERABLE_PERSIST_KEYS: string[] = Object.values(PERSIST_KEYS)
