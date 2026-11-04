/**
 * Selecting rows in a peek to total them.
 *
 * A row click used to open the register, so the only way to add up three
 * charges was by hand. Now a click selects and each row's arrow opens it.
 * The total is summed in cents (`sumAmounts`) and covers only rows on
 * screen, so changing the account filter clears it.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const rows = [
  { id: 't1', date: '2026-11-01', amount: -182.4, memo: null, import_description: 'Costco' },
  { id: 't2', date: '2026-11-02', amount: 12.99, memo: null, import_description: 'Costco refund' },
  { id: 't3', date: '2026-11-03', amount: -23.85, memo: null, import_description: 'Safeway' },
].map((r) => ({ ...r, account_id: 'visa', category_id: 'c1', payee_id: null }))

vi.mock('../../../api/transactions', () => ({
  useTransactionsPeek: () => ({
    data: { transactions: rows, total_count: rows.length, total_amount: -193.26 },
    isPending: false,
  }),
  useTransactionsPeekMonths: () => [],
  usePayees: () => ({ data: [] }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [
      { id: 'visa', name: 'Sapphire Visa', is_closed: false },
      { id: 'chk', name: 'Harborstone Checking', is_closed: false },
    ],
  }),
}))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
const navigate = vi.hoisted(() => vi.fn())
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))

import { TransactionsPeekModal } from './TransactionsPeekModal'

const SCOPE = {
  kind: 'category',
  categoryId: 'c1',
  categoryName: 'Groceries',
  month: '2026-11-01',
} as const

function rowOf(payee: string) {
  return screen.getByText(payee).closest('tr') as HTMLElement
}

beforeEach(() => {
  document.body.innerHTML = ''
  navigate.mockClear()
})

describe('selecting rows to total them', () => {
  it('selects on click instead of leaving for the register', () => {
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)
    fireEvent.click(rowOf('Costco'))
    expect(navigate).not.toHaveBeenCalled()
    expect(rowOf('Costco').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('1 selected')).toBeTruthy()
  })

  it('totals the selection in cents, signs and all', () => {
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)
    fireEvent.click(rowOf('Costco'))
    fireEvent.click(rowOf('Costco refund'))
    fireEvent.click(rowOf('Safeway'))
    expect(screen.getByText('3 selected')).toBeTruthy()
    expect(screen.getByText('-$193.26')).toBeTruthy()
    // A second click takes a row back out.
    fireEvent.click(rowOf('Costco refund'))
    expect(screen.getByText('-$206.25')).toBeTruthy()
  })

  it('toggles from the keyboard', () => {
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)
    fireEvent.keyDown(rowOf('Safeway'), { key: ' ' })
    expect(rowOf('Safeway').getAttribute('aria-selected')).toBe('true')
    fireEvent.keyDown(rowOf('Safeway'), { key: 'Enter' })
    expect(rowOf('Safeway').getAttribute('aria-selected')).toBe('false')
  })

  it('opens the register from the row’s arrow, without selecting it', () => {
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)
    fireEvent.click(
      within(rowOf('Safeway')).getByRole('button', { name: 'Open in account register' })
    )
    expect(navigate).toHaveBeenCalledWith('/accounts/visa?highlight=t3')
    expect(screen.queryByText(/selected$/)).toBeNull()
  })

  it('clears when the list changes under it', () => {
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)
    fireEvent.click(rowOf('Costco'))
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter by account' }), {
      target: { value: 'chk' },
    })
    expect(screen.queryByText('1 selected')).toBeNull()
  })

  it('clears from the footer', () => {
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)
    fireEvent.click(rowOf('Costco'))
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(rowOf('Costco').getAttribute('aria-selected')).toBe('false')
  })
})
