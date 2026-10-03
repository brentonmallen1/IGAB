import { describe, expect, it } from 'vitest'
import { transactionDisplayPayee } from './transferDisplay'

const payees = new Map([
  ['p-grocer', 'Corner Grocer'],
  ['p-to-savings', 'Transfer : Savings'],
])
const accounts = new Map([
  ['a-savings', 'Savings'],
  ['a-checking', 'Checking'],
])

describe('transactionDisplayPayee', () => {
  it('names the destination for a linked leg, even with no payee', () => {
    // The regression this helper exists for: linked legs rendered the bare
    // word 'Transfer', destination discarded.
    const txn = { payee_id: null, transfer_id: 't2', counterpart_account_id: 'a-savings' }
    expect(transactionDisplayPayee(txn, payees, accounts)).toBe('Transfer : Savings')
  })

  it('prefers the served counterpart over a stale payee', () => {
    // After a retarget the link is truth; the payee may still name the old
    // destination.
    const txn = {
      payee_id: 'p-to-savings',
      transfer_id: 't2',
      counterpart_account_id: 'a-checking',
    }
    expect(transactionDisplayPayee(txn, payees, accounts)).toBe('Transfer : Checking')
  })

  it('falls back to the transfer payee name when the account is unknown', () => {
    const txn = { payee_id: 'p-to-savings', transfer_id: null, counterpart_account_id: 'a-gone' }
    expect(transactionDisplayPayee(txn, payees, accounts)).toBe('Transfer : Savings')
  })

  it('says Transfer rather than — when it can name nothing else', () => {
    const txn = { payee_id: null, transfer_id: 't2', counterpart_account_id: null }
    expect(transactionDisplayPayee(txn, payees, accounts)).toBe('Transfer')
  })

  it('renders ordinary payees and empty rows unchanged', () => {
    expect(
      transactionDisplayPayee(
        { payee_id: 'p-grocer', transfer_id: null, counterpart_account_id: null },
        payees,
        accounts
      )
    ).toBe('Corner Grocer')
    expect(
      transactionDisplayPayee(
        { payee_id: null, transfer_id: null, counterpart_account_id: null },
        payees,
        accounts
      )
    ).toBe('—')
  })

  it('names a split leg by the served payee of record, not —', () => {
    // The budget's Activity peek drew '—' beside the Groceries share of a
    // wholesale-club receipt: the leg has no payee, its parent does.
    const leg = {
      payee_id: null,
      payee_of_record_id: 'p-grocer',
      transfer_id: null,
      counterpart_account_id: null,
    }
    expect(transactionDisplayPayee(leg, payees, accounts)).toBe('Corner Grocer')
  })

  it('still reads payee_id for a row shape without the served field', () => {
    expect(transactionDisplayPayee({ payee_id: 'p-grocer' }, payees, accounts)).toBe(
      'Corner Grocer'
    )
  })

  it('works without an account map (loading, or callers without one)', () => {
    const txn = { payee_id: 'p-to-savings', transfer_id: 't2', counterpart_account_id: 'a-savings' }
    expect(transactionDisplayPayee(txn, payees)).toBe('Transfer : Savings')
  })
})
