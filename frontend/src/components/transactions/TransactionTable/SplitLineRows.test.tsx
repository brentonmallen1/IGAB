/**
 * A split's lines under its register row: category, memo and money, read-only,
 * and a click that opens the split by the parent's own category-cell rule.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SplitLineRows } from './SplitLineRows'
import { makeTransaction } from '../../../test-utils/factories'
import type { Transaction } from '../../../types'

const h = vi.hoisted(() => ({ isMobile: false }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => h.isMobile }))

const categoryMap = new Map([
  ['cat-groceries', 'Groceries'],
  ['cat-household', 'Household'],
])

const parent = makeTransaction({ id: 'parent-1', amount: -100, is_split: true })
const lines: Transaction[] = [
  makeTransaction({
    id: 'line-1',
    amount: -60,
    category_id: 'cat-groceries',
    memo: 'weekly shop',
    parent_transaction_id: 'parent-1',
  }),
  makeTransaction({
    id: 'line-2',
    amount: -45,
    category_id: 'cat-household',
    parent_transaction_id: 'parent-1',
  }),
  makeTransaction({
    id: 'line-3',
    amount: 5,
    needs_category: true,
    memo: 'coupon',
    parent_transaction_id: 'parent-1',
  }),
]

function renderLines(over: Partial<Parameters<typeof SplitLineRows>[0]> = {}) {
  const props = {
    parent,
    lines,
    categoryMap,
    accountOnBudget: true,
    onStartSplit: vi.fn(),
    onEdit: vi.fn(),
    ...over,
  }
  const view = render(<SplitLineRows {...props} />)
  return { ...view, props }
}

describe('SplitLineRows', () => {
  it('draws each line: category, memo and amount, in order', () => {
    const { container } = renderLines()
    const rows = [...container.querySelectorAll('.split-line')]
    expect(rows).toHaveLength(3)
    expect(rows.map((r) => r.querySelector('.split-line__category')?.textContent)).toEqual([
      'Groceries',
      'Household',
      'Needs Category',
    ])
    expect(rows[0].querySelector('.split-line__memo')?.textContent).toBe('weekly shop')
    expect(rows[1].querySelector('.split-line__memo')?.textContent).toBe('')
    expect(rows[0].textContent).toContain('60.00')
    expect(rows[1].textContent).toContain('45.00')
  })

  it('puts money under OUTFLOW or INFLOW by its sign, as the row above does', () => {
    const { container } = renderLines()
    const amounts = [...container.querySelectorAll('.split-line__amount')]
    expect(amounts[0]).toHaveClass('split-line__amount--out')
    expect(amounts[2]).toHaveClass('split-line__amount--in')
    // Unsigned: the column says which way it went.
    expect(amounts[2].textContent).not.toContain('-')
  })

  it('opens the split editor when a line is clicked', () => {
    const { props } = renderLines()
    fireEvent.click(screen.getByText('Household'))
    expect(props.onStartSplit).toHaveBeenCalledWith(parent)
    expect(props.onEdit).not.toHaveBeenCalled()
  })

  it('opens the full editor for a reconciled split, as its category cell does', () => {
    const reconciled = { ...parent, cleared: 'reconciled' } as Transaction
    const { props } = renderLines({ parent: reconciled })
    fireEvent.click(screen.getByText('Groceries'))
    expect(props.onEdit).toHaveBeenCalledWith(reconciled)
    expect(props.onStartSplit).not.toHaveBeenCalled()
  })

  it('is read-only on a tracking account — no buttons to press', () => {
    renderLines({ accountOnBudget: false })
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('is read-only on a phone, where the row itself is the tap target', () => {
    h.isMobile = true
    try {
      renderLines()
      expect(screen.queryAllByRole('button')).toHaveLength(0)
    } finally {
      h.isMobile = false
    }
  })

  it('draws nothing while the lines are loading, or for a split with none', () => {
    expect(renderLines({ lines: undefined }).container).toBeEmptyDOMElement()
    expect(renderLines({ lines: [] }).container).toBeEmptyDOMElement()
  })
})
