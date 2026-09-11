/**
 * resolveGroupBy: tabs share one stored group-by, but not every tab can draw
 * every mode. "Payee" picked on the pareto reached the treemap as-is, which
 * silently drew group tiles under a highlighted Payee button — group names
 * where the user asked for payees.
 */
import { describe, expect, it } from 'vitest'
import { incomeDrill, resolveGroupBy } from './reportStore'

describe('resolveGroupBy', () => {
  it('keeps a mode the tab can draw', () => {
    expect(resolveGroupBy('pareto', 'payee')).toBe('payee')
    expect(resolveGroupBy('treemap', 'group')).toBe('group')
    expect(resolveGroupBy('treemap', 'category')).toBe('category')
  })

  it('falls back when the treemap is handed payee', () => {
    expect(resolveGroupBy('treemap', 'payee')).toBe('group')
  })

  it('leaves tabs without a group-by control alone', () => {
    expect(resolveGroupBy('net-worth', 'payee')).toBe('payee')
  })
})

describe('incomeDrill', () => {
  // The Sankey's Income node drilled parent rows. A split paycheck of +1,000
  // pay and -300 fees is one +700 parent, so a node reading 1,000 opened a
  // list totalling 700. Income is leaf rows of the income class, everywhere.
  it('lists the leaf rows every income figure counts', () => {
    const window = { startDate: '2026-08-01', endDate: '2026-08-31' }
    expect(incomeDrill('Income', window)).toEqual({
      kind: 'month',
      label: 'Income',
      scope: 'leaf',
      direction: 'inflow',
      activityClasses: ['income'],
      ...window,
    })
  })
})
