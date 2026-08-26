import { describe, expect, it } from 'vitest'
import { nextEditableField, isFieldEditable } from './fieldOrder'

const plain = { isTransfer: false, isSplit: false, onBudget: true }

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
    const ctx = { isTransfer: true, isSplit: true, onBudget: true }
    expect(nextEditableField('date', 1, ctx)).toBe('memo')
  })
})
