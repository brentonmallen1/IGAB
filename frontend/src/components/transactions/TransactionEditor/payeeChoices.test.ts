import { describe, expect, it } from 'vitest'
import type { Account, Payee } from '../../../types'
import { payeeChoices } from './payeeChoices'

const accounts = [
  { id: 'acc-checking', name: 'Harborstone Checking' },
  { id: 'acc-hysa', name: 'Cascade Point HYSA' },
] as Account[]
const payees = [
  { id: 'p-grocer', name: 'Harbor Grocer', transfer_account_id: null },
  {
    id: 'p-to-checking',
    name: 'Transfer : Harborstone Checking',
    transfer_account_id: 'acc-checking',
  },
] as Payee[]

function choices(query: string, shownTransferLabel: string | null = null) {
  return payeeChoices({ query, payees, accounts, targets: accounts, shownTransferLabel })
}

describe('payeeChoices', () => {
  it('offers the account, never its transfer payee, for a name both share', () => {
    const { payees: names, transfers } = choices('Harbor')
    expect(names.map((p) => p.id)).toEqual(['p-grocer'])
    expect(transfers.map((a) => a.id)).toEqual(['acc-checking'])
  })

  it("finds destinations by the register's wording", () => {
    expect(choices('Transfer').transfers.map((a) => a.id)).toEqual(['acc-checking'])
  })

  it('treats a box showing the destination as a reading, not a search', () => {
    const label = 'Transfer : Harborstone Checking'
    expect(choices(label, label).transfers).toHaveLength(2)
  })
})
