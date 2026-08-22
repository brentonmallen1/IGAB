// One place that turns a liability's `liability_type` into words.
//
// The value means different things on either side of the managed/unmanaged
// line, which is why three components each grew their own map and the three
// disagreed ("Auto" vs "Auto loan" vs "Auto loan"):
//
// - Managed: an ACCOUNT TYPE key, resolved by the backend from the linked
//   account. Built-in or custom, so the registry has the label — including for
//   a user's own "HELOC", which no hard-coded map could know about.
// - Unmanaged: the stored liability kind, whose vocabulary includes `personal`
//   and `medical` — things nobody creates an account for.
//
// Falls back through registry → legacy kinds → a humanised key, so an
// unrecognised value reads as itself rather than as "Other".

import type { AccountTypeInfo } from '../api/accountTypes'
import { BUILTIN_ACCOUNT_TYPES } from '../constants/accountTypes'

/** Kinds that only ever appear on an unmanaged liability — no account type
 *  corresponds to them, so the registry cannot answer. */
const UNMANAGED_KIND_LABELS: Record<string, string> = {
  mortgage: 'Mortgage',
  auto: 'Auto loan',
  student: 'Student loan',
  personal: 'Personal loan',
  credit_card: 'Credit card',
  medical: 'Medical',
  other: 'Other',
}

function humanise(key: string): string {
  return key
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function liabilityTypeLabel(
  liabilityType: string | null | undefined,
  accountTypes?: AccountTypeInfo[]
): string {
  if (!liabilityType) return 'Other'
  // The live registry first: it is the only source that knows custom types,
  // and a user who renamed a built-in expects to see their name.
  const registered = accountTypes?.find((t) => t.key === liabilityType)
  if (registered) return registered.label
  const builtin = BUILTIN_ACCOUNT_TYPES.find((t) => t.key === liabilityType)
  if (builtin) return builtin.label
  return UNMANAGED_KIND_LABELS[liabilityType] ?? humanise(liabilityType)
}
