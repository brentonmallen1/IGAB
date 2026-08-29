import { describe, expect, it } from 'vitest'
import { rowMayCarryCategory } from './rowCategoryRule'

// Mirrors backend/tests/unit/test_transfer_category_rule.py — one rule,
// one implementation per side.
describe('rowMayCarryCategory', () => {
  it('an on-budget plain row may', () => {
    expect(rowMayCarryCategory(true)).toBe(true)
    expect(rowMayCarryCategory(true, null)).toBe(true)
  })

  it('an off-budget plain row never may', () => {
    expect(rowMayCarryCategory(false)).toBe(false)
    expect(rowMayCarryCategory(false, null)).toBe(false)
  })

  it('a transfer leg may only when on-budget with an off-budget partner', () => {
    expect(rowMayCarryCategory(true, false)).toBe(true)
    expect(rowMayCarryCategory(true, true)).toBe(false)
    expect(rowMayCarryCategory(false, true)).toBe(false)
    expect(rowMayCarryCategory(false, false)).toBe(false)
  })
})
