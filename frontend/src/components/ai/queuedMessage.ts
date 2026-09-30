/**
 * What the app says when AI work is handed off — a scanned receipt or a
 * described transaction. Both are queued the same way and land the same way,
 * so they say it the same way: where it will turn up, and, with no account,
 * that it is not in the budget yet.
 */
export function queuedMessage(
  kind: 'receipt' | 'description',
  count: number,
  unplaced: boolean
): string {
  const one = count === 1
  const what =
    kind === 'receipt' ? (one ? 'Receipt' : 'receipts') : one ? 'Description' : 'descriptions'
  const head = one ? `${what} queued` : `${count} ${what} queued`
  if (unplaced) {
    return one
      ? `${head} — it waits in AI Activity until it has an account, and isn't in your budget until then`
      : `${head} — they wait in AI Activity until they have an account, and aren't in your budget until then`
  }
  return one
    ? `${head} — it'll show up in your transactions to review`
    : `${head} — they'll show up in your transactions to review`
}
