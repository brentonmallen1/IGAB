/**
 * Equity: what an asset is worth minus what is owed on everything secured by
 * it. One home for one money rule — it renders on both the AssetPage and the
 * LiabilityPage, and two spellings of a subtraction is how the two pages
 * would come to disagree about one house.
 *
 * Client-side by the boundary rule: pure presentational composition of
 * served figures — the asset's stated value and each liability's
 * `current_balance`, which the server already serves NORMALISED ("owed,
 * positive"). Never re-derive owed from a raw ledger balance: a managed
 * mortgage's ledger balance is negative when money is owed while an
 * unmanaged one's is stored positive, and subtracting the raw figure would
 * ADD a managed mortgage to equity.
 */

interface LinkedLiabilityLike {
  linked_asset_id: string | null
  /** Owed, positive — the served normalisation. */
  current_balance: number
}

export function liabilitiesSecuredBy<T extends LinkedLiabilityLike>(
  assetId: string,
  liabilities: T[]
): T[] {
  return liabilities.filter((l) => l.linked_asset_id === assetId)
}

/** Null when the asset has no stated value yet — "no honest number to show"
 *  beats an equity of −owed that reads as underwater. */
export function equityOf(
  value: number | null,
  assetId: string,
  liabilities: LinkedLiabilityLike[]
): number | null {
  if (value === null) return null
  const owed = liabilitiesSecuredBy(assetId, liabilities).reduce(
    (sum, l) => sum + l.current_balance,
    0
  )
  return value - owed
}
