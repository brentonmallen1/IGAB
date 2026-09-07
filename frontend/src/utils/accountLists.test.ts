/**
 * Choosing an account and naming one are different questions.
 *
 * The all-accounts register answered both from the same list — the open
 * accounts — and so drew "—" in the account column for every row on a closed
 * one, transfer legs naming a closed counterpart included. A YNAB import that
 * closed its dormant accounts on the way in produced a register full of
 * blanks; it was reported as "when I look in the transaction log, there is no
 * account for that".
 *
 * These are one-liners on purpose. The value is not the arithmetic, it is that
 * the distinction has a name and a home — it had been spelled inline six
 * times, and six copies of a filter is how the seventh gets written wrong.
 */
import { describe, expect, it } from 'vitest'
import { accountNameMap, closedAccounts, openAccounts } from './accountLists'

const ACCOUNTS = [
  { id: 'a1', name: 'Harborstone Checking', is_closed: false },
  { id: 'a2', name: 'First National (old)', is_closed: true },
  { id: 'a3', name: 'Sapphire Visa', is_closed: false },
]

describe('openAccounts', () => {
  it('offers only what is still open', () => {
    expect(openAccounts(ACCOUNTS).map((a) => a.id)).toEqual(['a1', 'a3'])
  })

  it('keeps the order it was given', () => {
    // The register assigns a palette slot by position. Reordering here would
    // reshuffle every account's identity colour.
    expect(openAccounts(ACCOUNTS)).toEqual([ACCOUNTS[0], ACCOUNTS[2]])
  })

  it('is the exact complement of closedAccounts', () => {
    expect(openAccounts(ACCOUNTS).length + closedAccounts(ACCOUNTS).length).toBe(ACCOUNTS.length)
    expect(closedAccounts(ACCOUNTS).map((a) => a.id)).toEqual(['a2'])
  })
})

describe('accountNameMap', () => {
  it('names a closed account, because its rows still exist', () => {
    // The defect, in one assertion.
    expect(accountNameMap(ACCOUNTS).get('a2')).toBe('First National (old)')
  })

  it('names every account it is given', () => {
    expect([...accountNameMap(ACCOUNTS).keys()]).toEqual(['a1', 'a2', 'a3'])
  })

  it('leaves a row unnamed only when the account is genuinely absent', () => {
    expect(accountNameMap(ACCOUNTS).get('gone')).toBeUndefined()
  })
})
