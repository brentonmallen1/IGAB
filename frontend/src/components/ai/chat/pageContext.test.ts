import { describe, expect, it } from 'vitest'
import { describePage } from './pageContext'

describe('describePage', () => {
  it('reads the budget grid with its month', () => {
    expect(describePage({ pathname: '/budget', selectedMonth: '2026-09-01' })).toEqual({
      kind: 'budget',
      month: '2026-09-01',
    })
  })

  it('names selected envelopes when there are some', () => {
    const context = describePage({
      pathname: '/budget',
      selectedMonth: '2026-09-01',
      selectedCategoryNames: ['Groceries', 'Dining'],
    })
    expect(context).toMatchObject({ selected_category_names: ['Groceries', 'Dining'] })
  })

  it('omits the selection key entirely when nothing is selected', () => {
    // An empty array reads as "they selected nothing", which is a different
    // claim from "there is no selection to report".
    const context = describePage({
      pathname: '/budget',
      selectedMonth: '2026-09-01',
      selectedCategoryNames: [],
    })
    expect(context).not.toHaveProperty('selected_category_names')
  })

  it('caps a long selection', () => {
    const names = Array.from({ length: 50 }, (_, i) => `Cat ${i}`)
    const context = describePage({
      pathname: '/budget',
      selectedMonth: '2026-09-01',
      selectedCategoryNames: names,
    })
    expect((context as { selected_category_names: string[] }).selected_category_names).toHaveLength(
      20
    )
  })

  it('reads the open report', () => {
    expect(describePage({ pathname: '/reports', reportTab: 'spending' })).toEqual({
      kind: 'reports',
      tab: 'spending',
    })
  })

  it('falls back to a default report tab', () => {
    expect(describePage({ pathname: '/reports' })).toEqual({ kind: 'reports', tab: 'overview' })
  })

  it('reads an account register by name, not by id', () => {
    expect(
      describePage({ pathname: '/accounts/abc-123', accountName: 'Harborstone Checking' })
    ).toEqual({ kind: 'account', account_name: 'Harborstone Checking' })
  })

  it('reads an account register with no name', () => {
    expect(describePage({ pathname: '/accounts/abc-123' })).toEqual({ kind: 'account' })
  })

  it('distinguishes the accounts list from one account', () => {
    expect(describePage({ pathname: '/accounts' })).toEqual({ kind: 'accounts' })
  })

  it.each([
    ['/transactions', 'transactions'],
    ['/liabilities', 'liabilities'],
    ['/assets', 'assets'],
    ['/guide', 'guide'],
    ['/wishlist', 'wishlist'],
    ['/scheduled', 'scheduled'],
    ['/payees', 'payees'],
    ['/settings', 'settings'],
    ['/ai-activity', 'ai-activity'],
    ['/activity', 'activity'],
    ['/import', 'import'],
  ])('reads %s', (pathname, kind) => {
    expect(describePage({ pathname })).toEqual({ kind })
  })

  it('reads a single liability and a single asset', () => {
    expect(describePage({ pathname: '/liabilities/x' })).toEqual({ kind: 'liability' })
    expect(describePage({ pathname: '/assets/x' })).toEqual({ kind: 'asset' })
  })

  it('ignores a trailing slash', () => {
    expect(describePage({ pathname: '/payees/' })).toEqual({ kind: 'payees' })
  })

  it('ignores a query string', () => {
    expect(describePage({ pathname: '/transactions?q=is%3A+unapproved' })).toEqual({
      kind: 'transactions',
    })
  })

  it('says nothing about a route it does not know', () => {
    // Telling the model someone is somewhere they are not is worse than
    // telling it nothing.
    expect(describePage({ pathname: '/somewhere-new' })).toBeNull()
    expect(describePage({ pathname: '/' })).toBeNull()
  })
})
