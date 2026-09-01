import { describe, expect, it } from 'vitest'
import { equityOf, liabilitiesSecuredBy } from './equity'

const liab = (assetId: string | null, owed: number) => ({
  linked_asset_id: assetId,
  current_balance: owed,
})

describe('equityOf', () => {
  it('subtracts everything secured by the asset — a house can carry two debts', () => {
    const liabilities = [liab('house', 200000), liab('house', 30000), liab('car', 8000)]
    expect(equityOf(300000, 'house', liabilities)).toBe(70000)
  })

  it('uses the served owed figure, so a managed mortgage subtracts', () => {
    // current_balance is served "owed, positive" for BOTH modes; the raw
    // ledger balance of a managed mortgage is negative and would have ADDED.
    expect(equityOf(300000, 'house', [liab('house', 286000)])).toBe(14000)
  })

  it('is null with no stated value — not an equity of minus-the-debt', () => {
    expect(equityOf(null, 'house', [liab('house', 200000)])).toBeNull()
  })

  it('is the full value when nothing is linked', () => {
    expect(equityOf(9000, 'car', [liab(null, 500)])).toBe(9000)
  })
})

describe('liabilitiesSecuredBy', () => {
  it('filters by the served link', () => {
    const all = [liab('house', 1), liab(null, 2), liab('car', 3)]
    expect(liabilitiesSecuredBy('house', all)).toHaveLength(1)
  })
})
