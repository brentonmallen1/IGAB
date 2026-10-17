/**
 * The drill-down's category column reads the register's label. It had its own
 * rule, which `categoryCell.test.ts` lists case by case; this pins that the
 * panel reads the shared one, with the group on hover.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useReportStore } from '../../../stores/reportStore'
import { makeTransaction } from '../../../test-utils/factories'
import type { Transaction } from '../../../types'
import { DrillDownPanel } from './DrillDownPanel'

const h = vi.hoisted(() => ({ rows: [] as unknown[] }))

vi.mock('../../../api/transactions', () => ({
  useBudgetTransactions: () => ({
    data: { transactions: h.rows, total_count: h.rows.length, total_amount: 0 },
    isLoading: false,
    isError: false,
  }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [
      { id: 'checking', name: 'Harborstone Checking', on_budget: true },
      { id: 'brokerage', name: 'Cascade Point Brokerage', on_budget: false },
    ],
  }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [
      { id: 'gifts-hols', name: 'Gifts', category_group_id: 'g-hols' },
      { id: 'gifts-bdays', name: 'Gifts', category_group_id: 'g-bdays' },
    ],
  }),
  useCategoryGroups: () => ({
    data: [
      { id: 'g-hols', name: 'Holidays' },
      { id: 'g-bdays', name: 'Birthdays' },
    ],
  }),
}))
vi.mock('../../../api/payees', () => ({ usePayees: () => ({ data: [] }) }))

function categoryColumn(rows: Partial<Transaction>[]): string[] {
  h.rows = rows.map((r, i) => makeTransaction({ id: `t${i}`, account_id: 'checking', ...r }))
  const { container } = render(<DrillDownPanel budgetId="b1" />)
  // Date, Account, Payee, Category, …
  return [...container.querySelectorAll('tbody tr')].map(
    (tr) => tr.querySelectorAll('td')[3].textContent ?? ''
  )
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
  useReportStore.setState({
    drillDown: {
      kind: 'category',
      label: 'Gifts',
      scope: 'leaf',
      startDate: '2026-08-01',
      endDate: '2026-08-31',
    } as never,
  })
})

describe('the drill-down category column', () => {
  it('reads each row the way the register does', () => {
    expect(
      categoryColumn([
        { category_id: 'gifts-hols' },
        { needs_category: true },
        { needs_category: false },
        { is_split: true },
        { counterpart_account_id: 'checking', account_id: 'brokerage' },
      ])
    ).toEqual(['Gifts', 'Needs Category', 'Transfer', 'Split', '—'])
  })

  it('names the group on hover, so two "Gifts" read apart', async () => {
    categoryColumn([{ category_id: 'gifts-bdays' }])
    fireEvent.mouseEnter(screen.getByText('Gifts'))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Birthdays › Gifts')
  })
})
