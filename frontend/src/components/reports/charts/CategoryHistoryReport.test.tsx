import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render as rtlRender, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as categoriesApi from '../../../api/categories'
import * as reportsApi from '../../../api/reports'
import { useReportStore } from '../../../stores/reportStore'
import { CategoryHistoryReport } from './CategoryHistoryReport'

vi.mock('../../../api/categories', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/categories')>()),
  useCategories: vi.fn(),
  useCategoryGroups: vi.fn(),
}))
vi.mock('../../../api/reports', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/reports')>()),
  useCategoryHistoryReport: vi.fn(),
}))

/** The range picker and export button read their own queries; they get a
 *  client that never fetches. */
function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } })
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const month = (m: string, over: Partial<Record<string, number | null>> = {}) => ({
  month: m,
  assigned: 100,
  activity: 0,
  spent: 100,
  moved_in: 0,
  moved_out: 0,
  available: 0,
  ...over,
})

beforeEach(() => {
  useReportStore.setState({ historyCategoryId: '' })
  vi.mocked(categoriesApi.useCategories).mockReturnValue({
    data: [
      { id: 'c1', name: 'Medical', category_group_id: 'g1', is_categorizable: true },
      { id: 'c2', name: 'Groceries', category_group_id: 'g1', is_categorizable: true },
    ],
  } as never)
  vi.mocked(categoriesApi.useCategoryGroups).mockReturnValue({
    data: [{ id: 'g1', name: 'Everyday' }],
  } as never)
  vi.mocked(reportsApi.useCategoryHistoryReport).mockImplementation(
    (_budget: string | null, categoryId: string | null) =>
      ({
        data: categoryId
          ? {
              category_id: categoryId,
              category_name: 'Medical',
              months: [
                month('2026-07-01', { spent: 70 }),
                // 2,000 moved in from savings paid a 2,000 bill: Activity nets
                // it to zero, Spent does not.
                month('2026-08-01', { assigned: 0, spent: 2000, moved_in: 2000, activity: 0 }),
                month('2026-09-01', { spent: 10, available: -20 }),
              ],
              average_spent: 1035,
              months_averaged: 2,
            }
          : undefined,
        isLoading: false,
        isError: false,
        refetch: () => {},
      }) as never
  )
})

describe('CategoryHistoryReport', () => {
  it('remembers the picked category across a remount', () => {
    // The pick lived in the report's own state, so leaving the tab dropped it
    // and the report opened on "Pick a category…" every time.
    const first = render(<CategoryHistoryReport budgetId="b1" />)
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'c1' } })
    first.unmount()

    render(<CategoryHistoryReport budgetId="b1" />)
    expect((screen.getByLabelText('Category') as HTMLSelectElement).value).toBe('c1')
    expect(useReportStore.getState().historyCategoryId).toBe('c1')
  })

  it('asks again when the remembered category is gone', () => {
    useReportStore.setState({ historyCategoryId: 'deleted' })
    render(<CategoryHistoryReport budgetId="b1" />)
    expect(screen.getByText('Pick a category to see its month-by-month history.')).toBeTruthy()
    expect(vi.mocked(reportsApi.useCategoryHistoryReport).mock.calls.at(-1)?.[1]).toBeNull()
  })

  it('reads the served Spent and its complete-month average, labelled net', () => {
    useReportStore.setState({ historyCategoryId: 'c1' })
    const { container } = render(<CategoryHistoryReport budgetId="b1" />)

    const cardValue = (label: string) =>
      screen
        .getByText(label, { selector: '.metric-card__label' })
        .closest('.metric-card')
        ?.querySelector('.metric-card__value')?.textContent
    const cardSub = (label: string) =>
      screen
        .getByText(label, { selector: '.metric-card__label' })
        .closest('.metric-card')
        ?.querySelector('.metric-card__sub')?.textContent

    // 70 + 2,000 + 10: the bill paid from savings is spending here, as on
    // every plan report. `max(-activity, 0)` read it as nothing.
    expect(cardValue('Spent (net of refunds)')).toBe('$2,080.00')
    // Served, over the two complete months — the running month's 10 is not
    // in it.
    expect(cardValue('Average spent')).toBe('$1,035.00')
    expect(cardSub('Average spent')).toBe('per month, over 2 complete months')
    // The table shows the money moved in beside Spent and Activity.
    const headers = [...container.querySelectorAll('th')].map((h) => h.textContent)
    expect(headers).toEqual(['Month', 'Assigned', 'Moved in', 'Spent', 'Activity', 'Available'])
  })

  it('states which accounts it reads', () => {
    useReportStore.setState({ historyCategoryId: 'c1' })
    render(<CategoryHistoryReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: 'About the Category History report' }))
    expect(screen.getByText(/^Accounts:/)).toBeTruthy()
  })
})
