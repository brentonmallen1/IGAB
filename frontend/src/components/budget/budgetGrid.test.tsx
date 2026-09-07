/**
 * The budget grid's column contract.
 *
 * A group header rendered its three totals one column to the right of their
 * headings — ASSIGNED under ACTIVITY, ACTIVITY under AVAILABLE, AVAILABLE
 * wrapped onto a second row — because the money cells were placed by grid
 * auto-flow and the header had one more child than the template had columns.
 * The arithmetic was right the whole time; a user reading the page saw a
 * budget whose group totals did not add up.
 *
 * jsdom has no layout, so this cannot assert pixels. It asserts the thing
 * that decides them: every cell of a `.budget-grid` row says which column it
 * is in, so no future sibling can shuffle the money sideways again.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { CategoryGroupRow } from './CategoryGroupRow/CategoryGroupRow'
import { makeCategory, makeCategoryBalance, makeCategoryGroup } from '../../test-utils/factories'
import type { CategoryBalance } from '../../types'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

// The shape the bug was reported in — a group holding a moved-out-of envelope
// (negative assigned) and two ordinary ones — with invented figures. Each
// column sums to something distinctive, so a total in the wrong column reads
// as wrong rather than plausible.
const CATEGORIES = [
  makeCategory({ id: 'c1', name: 'Groceries' }),
  makeCategory({ id: 'c2', name: 'Fuel' }),
  makeCategory({ id: 'c3', name: 'Pharmacy' }),
]
const BALANCES = new Map<string, CategoryBalance>([
  ['c1', makeCategoryBalance({ category_id: 'c1', assigned: 480, activity: 0, available: 512.4 })],
  [
    'c2',
    makeCategoryBalance({ category_id: 'c2', assigned: -90, activity: -12.5, available: 104.25 }),
  ],
  [
    'c3',
    makeCategoryBalance({ category_id: 'c3', assigned: 305, activity: -148.75, available: 233.6 }),
  ],
])

function renderGroup() {
  return render(
    <CategoryGroupRow
      group={makeCategoryGroup({ name: 'Everyday' })}
      categories={CATEGORIES}
      balanceMap={BALANCES}
      budgetId="b1"
      month="2026-08-01"
      index={0}
    />,
    { wrapper }
  )
}

/** Every `.budget-grid` row in the tree, header and category rows alike. */
function gridRows(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>('.budget-grid')]
}

describe('group totals land under their own headings', () => {
  it('puts each total in the cell that names its column', () => {
    const { container } = renderGroup()
    const header = container.querySelector<HTMLElement>('.category-group-row__header')!

    // 480 − 90 + 305, 0 − 12.50 − 148.75, 512.40 + 104.25 + 233.60
    expect(within(header).getByText('$695.00')).toHaveClass('budget-grid__assigned')
    expect(within(header).getByText('-$161.25')).toHaveClass('budget-grid__activity')
    expect(within(header).getByText('$850.25')).toHaveClass('budget-grid__available')
  })

  it('sums with the shared rule, so an income row is left out', () => {
    // `sumBalances` skips a row the server serves with null assigned/available:
    // its activity is income received, not spending. The group header used to
    // reduce inline with `?? 0` and counted it.
    const balances = new Map(BALANCES)
    balances.set(
      'c4',
      makeCategoryBalance({ category_id: 'c4', assigned: null, activity: 2400, available: null })
    )
    const { container } = render(
      <CategoryGroupRow
        group={makeCategoryGroup({ name: 'Everyday' })}
        categories={[...CATEGORIES, makeCategory({ id: 'c4', name: 'Paycheque' })]}
        balanceMap={balances}
        budgetId="b1"
        month="2026-08-01"
        index={0}
      />,
      { wrapper }
    )
    const header = container.querySelector<HTMLElement>('.category-group-row__header')!
    expect(within(header).getByText('-$161.25')).toHaveClass('budget-grid__activity')
  })
})

describe('every budget-grid cell declares its column', () => {
  // Two children are deliberately not grid cells, and both say why here rather
  // than in an assertion nobody can read:
  //   - the drag grip is absolutely positioned in the row's left padding, so
  //     it takes no track (see DragHandle.css);
  //   - the collapsed-group summary is `display: none` above 768px, and is
  //     placed explicitly in the mobile block that shows it.
  const OUT_OF_FLOW = ['drag-handle', 'category-group-row__mobile-summary']
  const PLACED = /^budget-grid__/

  it('holds for the group header and every category row under it', () => {
    const { container } = renderGroup()
    const rows = gridRows(container)
    expect(rows.length).toBe(1 + CATEGORIES.length)

    for (const row of rows) {
      for (const cell of [...row.children]) {
        const classes = [...cell.classList]
        if (classes.some((c) => OUT_OF_FLOW.includes(c))) continue
        expect(
          classes.some((c) => PLACED.test(c)),
          `${row.className.split(' ')[0]} > ${cell.tagName.toLowerCase()}.${classes.join('.')} ` +
            'is a grid item with no column. Give it a budget-grid__* class, or take it ' +
            'out of flow — auto-flow placing it will move the money columns.'
        ).toBe(true)
      }
    }
  })

  it('still holds while a group is being renamed', () => {
    // Renaming swaps the name for an input and drops the action buttons, which
    // is a different child count — the shape that used to render correctly
    // while the resting one did not.
    const { container } = renderGroup()
    screen.getByText('Everyday').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))

    for (const cell of [...container.querySelector('.category-group-row__header')!.children]) {
      const classes = [...cell.classList]
      if (classes.some((c) => OUT_OF_FLOW.includes(c))) continue
      expect(classes.some((c) => PLACED.test(c))).toBe(true)
    }
  })
})
