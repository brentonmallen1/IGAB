/**
 * The palette's search.
 *
 * The reported bug: typing "12.34" returned nothing while "12" worked, so it
 * looked like the dot broke search. It wasn't the server — cmdk's default
 * filter re-scored the rows the server had already matched, against each
 * item's `value` + `keywords`. A transaction's amount is rendered but is in
 * neither, so every row scored zero and "No results" covered a correct
 * answer. ("12" only survived because those digits appear inside a hex uuid.)
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const navigate = vi.hoisted(() => vi.fn())
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('../../../api/client', () => ({ apiClient: { get: apiGet } }))

const ACCOUNTS = vi.hoisted(() => [{ id: 'acc-1', name: 'Checking', on_budget: true }])
const PAYEES = vi.hoisted(() => [{ id: 'p-1', name: 'Corner Grocer' }])
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: ACCOUNTS }) }))
vi.mock('../../../api/payees', () => ({ usePayees: () => ({ data: PAYEES }) }))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../../../api/budgetFilters', () => ({ useBudgetFilters: () => ({ data: [] }) }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../../../hooks/useHistoryDismissable', () => ({ useHistoryDismissable: () => {} }))
vi.mock('../../../hooks/useShortcut', () => ({ useShortcut: () => {} }))

import { CommandPalette } from './CommandPalette'
import { useUIStore } from '../../../stores/uiStore'
import { useAppStore } from '../../../stores/appStore'

const TXN = {
  id: '3a1f0000-0000-4000-8000-00000000c2ab',
  account_id: 'acc-1',
  date: '2026-08-20',
  amount: '-12.34',
  payee_id: 'p-1',
  memo: null,
}

function renderPalette() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <CommandPalette />
    </QueryClientProvider>
  )
}

/** The palette debounces by 250ms before it asks the server. */
async function type(text: string) {
  await userEvent.type(screen.getByPlaceholderText(/Search commands/), text)
  await vi.advanceTimersByTimeAsync(300)
}

describe('CommandPalette search', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    navigate.mockClear()
    apiGet.mockReset()
    apiGet.mockResolvedValue({ data: { transactions: [TXN], total_count: 1, total_amount: '0' } })
    useAppStore.setState({ currentBudgetId: 'b1' })
    useUIStore.setState({ isPaletteOpen: true })
  })

  it('shows a transaction matched on its amount, dot and all', async () => {
    renderPalette()
    await type('12.34')

    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(await screen.findByText('Corner Grocer')).toBeInTheDocument()
    expect(screen.queryByText('No results.')).not.toBeInTheDocument()
  })

  it('sends the amount as a filter, not just as free text', async () => {
    renderPalette()
    await type('amount:>100')

    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    const params = apiGet.mock.calls.at(-1)![1].params
    expect(params.amount_min).toBe(100)
  })

  it('understands the date language the register taught the user', async () => {
    renderPalette()
    await type('date: 2026-03-15')

    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    const params = apiGet.mock.calls.at(-1)![1].params
    expect(params.start_date).toBe('2026-03-15')
    expect(params.end_date).toBe('2026-03-15')
  })

  it('offers the whole dataset, not just the ten rows it previews', async () => {
    renderPalette()
    await type('grocer')

    const openAll = await screen.findByText(/Search all transactions/)
    await userEvent.click(openAll)
    expect(navigate).toHaveBeenCalledWith('/transactions?q=grocer')
  })

  it('still filters the fixed command list by what was typed', async () => {
    // shouldFilter={false} hands this job to us; getting it wrong would show
    // every command under every query.
    renderPalette()
    await type('zzzznotacommand')
    expect(screen.queryByText('Add Transaction')).not.toBeInTheDocument()
  })

  it('finds an account by name', async () => {
    renderPalette()
    await type('check')
    expect(screen.getByText('Checking')).toBeInTheDocument()
  })
})

describe('CommandPalette search syntax help', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    apiGet.mockReset()
    apiGet.mockResolvedValue({ data: { transactions: [], total_count: 0, total_amount: '0' } })
    useAppStore.setState({ currentBudgetId: 'b1' })
    useUIStore.setState({ isPaletteOpen: true })
  })

  it('offers the filter vocabulary once a query looks like a token', async () => {
    renderPalette()
    await type('date:')
    expect(screen.getByText('date:')).toBeInTheDocument()
  })

  it('stays out of the way for an ordinary word', async () => {
    // Burying real rows under syntax help is how a search box starts feeling
    // like a manual.
    renderPalette()
    await type('grocer')
    expect(screen.queryByText(/On a date or range/)).not.toBeInTheDocument()
  })

  it('completes the query in place instead of running something', async () => {
    renderPalette()
    await type('amount:')
    await userEvent.click(screen.getByText('amount:>'))
    expect(screen.getByPlaceholderText(/Search commands/)).toHaveValue('amount:>')
    expect(navigate).not.toHaveBeenCalled()
  })
})
