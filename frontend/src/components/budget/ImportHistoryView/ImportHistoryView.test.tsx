/**
 * A month before the import shows YNAB's own figures, read-only, and says
 * so — with the way to edit it named, not hidden.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ImportHistoryView } from './ImportHistoryView'

vi.mock('../../../api/budgets', () => ({
  useImportHistoryMonth: () => ({
    data: {
      month: '2026-07-01',
      import_month: '2026-08-01',
      history_starts: '2026-06-01',
      rows: [
        {
          category_group: 'Bills',
          category: 'Utilities',
          category_id: 'c1',
          assigned: 100,
          activity: -150,
          available: -50,
        },
        {
          category_group: 'Bills',
          category: 'Old Gym',
          category_id: null,
          assigned: 0,
          activity: null,
          available: null,
        },
      ],
    },
    isLoading: false,
    isError: false,
  }),
}))

function show() {
  render(
    <MemoryRouter>
      <ImportHistoryView budgetId="b1" month="2026-07-01" importMonth="2026-08-01" />
    </MemoryRouter>
  )
}

describe('a read-only month before the import', () => {
  it('says whose figures these are and where the budget starts', () => {
    show()
    expect(screen.getByRole('note')).toHaveTextContent(
      /YNAB.s own figures for July 2026.*your budget starts in August 2026/
    )
    expect(screen.getByRole('link', { name: 'Edit months before the import' })).toHaveAttribute(
      'href',
      '/settings/budget'
    )
  })

  it('shows each category as YNAB had it, and a dash for a figure the export lacked', () => {
    show()
    const utilities = screen.getByRole('row', { name: /Utilities/ })
    expect(utilities).toHaveTextContent('-$50.00')
    const gym = screen.getByRole('row', { name: /Old Gym/ })
    expect(gym).toHaveTextContent('—')
  })
})
