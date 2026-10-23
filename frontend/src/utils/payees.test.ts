import { describe, expect, it } from 'vitest'
import { choosablePayees, isTransferPayee } from './payees'

const PAYEES = [
  { id: 'p-grocer', name: 'Harbor Grocer', transfer_account_id: null },
  { id: 'p-to-hysa', name: 'Transfer : Cascade Point HYSA', transfer_account_id: 'acc-hysa' },
  // A real payee that merely sounds like a transfer is still a payee.
  { id: 'p-online', name: 'Online Transfer', transfer_account_id: null },
]

describe('choosablePayees', () => {
  it('drops the payees the server made to name an account', () => {
    expect(choosablePayees(PAYEES).map((p) => p.id)).toEqual(['p-grocer', 'p-online'])
  })

  it('judges by the link, never the name', () => {
    expect(isTransferPayee(PAYEES[2])).toBe(false)
    expect(isTransferPayee(PAYEES[1])).toBe(true)
  })
})
