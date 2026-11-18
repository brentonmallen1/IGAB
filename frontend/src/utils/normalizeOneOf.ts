/**
 * A stored value read back as one of a closed list, or the fallback.
 *
 * For device settings persisted as strings (appStore): a value an older or
 * newer build wrote, or junk, reads as the default rather than as an
 * attribute no stylesheet rule matches. Pair it with an `as const` list the
 * type is derived from, so the list and the type cannot disagree.
 */
export function normalizeOneOf<T extends string>(
  options: readonly T[],
  value: unknown,
  fallback: T
): T {
  return options.includes(value as T) ? (value as T) : fallback
}
