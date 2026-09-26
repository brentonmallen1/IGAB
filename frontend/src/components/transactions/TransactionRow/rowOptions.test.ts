/**
 * The filter behind the register row's payee picker.
 *
 * Not cosmetic: a transfer payee picked as a payee names a transfer the row
 * is not. The category picker's list is `filingCategoryOptions`, tested in
 * utils/categoryPickers.test.ts with every other picker that files a leg.
 */
import { describe, expect, it } from 'vitest'
import { payeeOptions } from './rowOptions'
import type { Payee } from '../../../types'

const payees = [
  { id: 'p1', name: 'Nordstrom', transfer_account_id: null },
  { id: 'p2', name: 'Transfer : Sapphire Visa', transfer_account_id: 'a2' },
] as unknown as Payee[]

describe('payeeOptions', () => {
  it('leaves out transfer payees — a destination is not a payee', () => {
    expect(payeeOptions(payees)).toEqual([{ id: 'p1', label: 'Nordstrom' }])
  })
})
