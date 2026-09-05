import { describe, expect, it } from 'vitest'
import { nextEditableField, isFieldEditable } from './fieldOrder'

// A single account's register: no account column, so no account cell to
// tab into. The all-accounts cases set `accountMovable` explicitly below.
const plain = { isTransfer: false, isSplit: false, onBudget: true, accountMovable: false }

describe('nextEditableField', () => {
  it('walks the row left to right and back', () => {
    expect(nextEditableField('date', 1, plain)).toBe('payee')
    expect(nextEditableField('category', 1, plain)).toBe('memo')
    expect(nextEditableField('memo', -1, plain)).toBe('category')
  })

  it('ends editing past either edge instead of wrapping', () => {
    expect(nextEditableField('inflow', 1, plain)).toBeNull()
    expect(nextEditableField('date', -1, plain)).toBeNull()
  })

  it('skips the payee of a linked transfer', () => {
    const ctx = { ...plain, isTransfer: true }
    expect(nextEditableField('date', 1, ctx)).toBe('category')
    expect(nextEditableField('category', -1, ctx)).toBe('date')
  })

  it("skips a split parent's category — its lines carry them", () => {
    const ctx = { ...plain, isSplit: true }
    expect(nextEditableField('payee', 1, ctx)).toBe('memo')
  })

  it('skips the category on an off-budget account', () => {
    const ctx = { ...plain, onBudget: false }
    expect(isFieldEditable('category', ctx)).toBe(false)
    expect(nextEditableField('payee', 1, ctx)).toBe('memo')
  })

  it('skips several unavailable cells in a row', () => {
    const ctx = { isTransfer: true, isSplit: true, onBudget: true, accountMovable: false }
    expect(nextEditableField('date', 1, ctx)).toBe('memo')
  })
})

describe('the account cell', () => {
  const allAccounts = { ...plain, accountMovable: true }

  it('sits between the date and the payee, where the column is drawn', () => {
    expect(nextEditableField('date', 1, allAccounts)).toBe('account')
    expect(nextEditableField('account', 1, allAccounts)).toBe('payee')
    expect(nextEditableField('payee', -1, allAccounts)).toBe('account')
  })

  it("is skipped in a single account's register, where there is no column", () => {
    // The account is the register there — a picker would be asking a
    // question the page has already answered.
    expect(isFieldEditable('account', plain)).toBe(false)
    expect(nextEditableField('date', 1, plain)).toBe('payee')
  })

  it('is skipped when the row is locked to its account', () => {
    // Bank-fed and reconciled rows: WHY is accountMove.ts's rule, which the
    // register asks before setting this flag. Here it is just a fact.
    expect(isFieldEditable('account', { ...allAccounts, accountMovable: false })).toBe(false)
  })
})
