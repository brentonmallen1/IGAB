/**
 * Reordering a list the user arranges by hand — the client half of the rule
 * `backend/src/igab/domain/ordering.py` states for the server.
 *
 * Both halves exist because a drag has to show its result before the round
 * trip. `listOrder.test.ts` pins the same cases as `tests/unit/test_ordering.py`,
 * by name, so the two cannot drift apart unnoticed.
 */

/** `list` with the item at `from` moved to `to`. Returns `list` itself when
 *  the move is a no-op or out of range, so callers can compare by identity. */
export function moveItem<T>(list: readonly T[], from: number, to: number): readonly T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) {
    return list
  }
  const next = [...list]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

/**
 * The members of `list` after the user reordered `orderedIds` — the members
 * they were shown. A member not named keeps its slot (a hidden row the grid
 * does not draw, a system group it never renders); the named ones fill the
 * remaining member slots in the given order. Everything that is not a member
 * stays where it was, and `sort_order` is renumbered by member position, so
 * anything reading it agrees with the order it is rendered in.
 */
export function reorderMembers<T extends { id: string; sort_order: number }>(
  list: readonly T[],
  isMember: (item: T) => boolean,
  orderedIds: readonly string[]
): T[] {
  const byId = new Map(list.filter(isMember).map((item) => [item.id, item]))
  const named = orderedIds.filter((id) => byId.has(id))
  const namedSet = new Set(named)
  let cursor = 0
  let position = 0
  return list.map((item) => {
    if (!isMember(item)) return item
    const next = namedSet.has(item.id) ? byId.get(named[cursor++])! : item
    return { ...next, sort_order: position++ }
  })
}
