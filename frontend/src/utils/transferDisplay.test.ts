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
    const txn = { payee_id: 'p-to-savings', transfer_id: 't2', counterpart_account_id: 'a-checking' }
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

  it('works without an account map (loading, or callers without one)', () => {
    const txn = { payee_id: 'p-to-savings', transfer_id: 't2', counterpart_account_id: 'a-savings' }
    expect(transactionDisplayPayee(txn, payees)).toBe('Transfer : Savings')
  })
})
