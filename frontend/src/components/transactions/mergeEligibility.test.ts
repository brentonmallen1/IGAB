/**
 * The shared merge cases, run on this side.
 *
 * Every case here is also run by backend/tests/unit/test_merge_offer.py
 * against the real server rule. A rule changed on one side only fails on the
 * other — which is the point: this copy had drifted, and the register
 * offered a merge the server refused on every save.
 */
import { describe, expect, it } from 'vitest'
import cases from '../../../../shared/merge_cases.json'
import { mayOfferMerge } from './mergeEligibility'
import type { Transaction } from '../../types'

type Side = {
  cleared: string
  account_id: string
  sync_id: string | null
  is_split?: boolean
  transfer_id?: string
  parent_transaction_id?: string
}

function side(spec: Side, id: string): Transaction {
  return {
    id,
    cleared: spec.cleared,
    account_id: spec.account_id,
    sync_id: spec.sync_id,
    is_split: !!spec.is_split,
    transfer_id: spec.transfer_id ?? null,
    parent_transaction_id: spec.parent_transaction_id ?? null,
  } as unknown as Transaction
}

describe('the shared merge cases', () => {
  for (const c of cases.cases) {
    it(c.note, () => {
      const a = side(c.a as Side, 'side-a')
      const b = side(c.b as Side, 'side-b')
      expect(mayOfferMerge(a, b)).toBe(c.register_offers)
      // Order is not part of the question: the register has no first row.
      expect(mayOfferMerge(b, a)).toBe(c.register_offers)
    })

    it(`${c.note} — never offered when the server would refuse`, () => {
      if (c.register_offers) expect(c.server_accepts).toBe(true)
    })
  }
})

describe('mayOfferMerge', () => {
  it('never offers a row against itself', () => {
    const t = side({ cleared: 'cleared', account_id: 'a1', sync_id: null }, 'same')
    expect(mayOfferMerge(t, t)).toBe(false)
  })

  it('offers a bank row against a hand-entered one — the id is only on one side', () => {
    const bank = side({ cleared: 'cleared', account_id: 'a1', sync_id: 'TRN-1' }, 'x')
    const manual = side({ cleared: 'uncleared', account_id: 'a1', sync_id: null }, 'y')
    expect(mayOfferMerge(bank, manual)).toBe(true)
  })
})
