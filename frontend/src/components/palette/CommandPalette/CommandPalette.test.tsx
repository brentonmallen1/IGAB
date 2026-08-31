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
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

// The palette applies the same gates the pages do, so it needs to know who is
// asking and which guide tabs are switched on.
const currentUser = vi.hoisted(() => vi.fn((): { data: unknown } => ({ data: undefined })))
const guideOverview = vi.hoisted(() => vi.fn((): { data: unknown } => ({ data: undefined })))
vi.mock('../../../api/auth', () => ({ useCurrentUser: currentUser }))
vi.mock('../../../api/guide', () => ({ useGuideOverview: guideOverview }))

import { CommandPalette } from './CommandPalette'
import { useUIStore } from '../../../stores/uiStore'
import { useAppStore } from '../../../stores/appStore'

const TXN = {
  id: '3a1f0000-0000-4000-8000-00000000c2ab',
  account_id: 'acc-1',
  date: '2026-08-20',
  amount: -12.34,
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

  it('names a transfer leg by its destination, like the register does', async () => {
    // The shared rule (transactionDisplayPayee) — the hand-rolled lookup this
    // replaced called every payee-less transfer "No payee" here while the
    // register said "Transfer : Checking" for the same row.
    apiGet.mockResolvedValue({
      data: {
        transactions: [
          { ...TXN, payee_id: null, transfer_id: 't-far', counterpart_account_id: 'acc-1' },
        ],
        total_count: 1,
        total_amount: '0',
      },
    })
    renderPalette()
    await type('12.34')

    expect(await screen.findByText('Transfer : Checking')).toBeInTheDocument()
    expect(screen.queryByText('No payee')).not.toBeInTheDocument()
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

describe('CommandPalette help', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    apiGet.mockReset()
    apiGet.mockResolvedValue({ data: { transactions: [], total_count: 0, total_amount: '0' } })
    useAppStore.setState({ currentBudgetId: 'b1' })
    useUIStore.setState({ isPaletteOpen: true })
  })

  it('explains the query language from inside the palette', async () => {
    renderPalette()
    await userEvent.click(screen.getByLabelText('How to search transactions'))
    expect(screen.getByText('Searching transactions')).toBeInTheDocument()
  })

  it('Escape closes the help without closing the palette underneath it', async () => {
    // Both listen for Escape. One press should dismiss the explanation the
    // user just opened, not the thing they were reading it about.
    renderPalette()
    await userEvent.click(screen.getByLabelText('How to search transactions'))
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByText('Searching transactions')).not.toBeInTheDocument()
    expect(useUIStore.getState().isPaletteOpen).toBe(true)
  })
})

/**
 * The rows the palette derives rather than a person writing them.
 *
 * The point of generating them is that a destination cannot be unreachable by
 * omission — so what these check is the gating, which generation makes easy to
 * get wrong in the other direction: offering a section the page will not
 * render.
 */
describe('CommandPalette derived destinations', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    navigate.mockClear()
    apiGet.mockReset()
    apiGet.mockResolvedValue({ data: { transactions: [], total_count: 0, total_amount: '0' } })
    useAppStore.setState({ currentBudgetId: 'b1' })
    useUIStore.setState({ isPaletteOpen: true })
    currentUser.mockReturnValue({ data: { id: 'u1', email: 'a@b.c', is_admin: false } })
    guideOverview.mockReturnValue({
      data: { preferences: { personalization: true, checkup: true, wishlist: true } },
    })
  })

  it('reaches a report tab by its own label', async () => {
    renderPalette()
    await type('net worth')
    await userEvent.click(await screen.findByText('Report: Net Worth'))
    expect(navigate).toHaveBeenCalledWith('/reports?tab=net-worth')
  })

  it('surfaces every report in a group when the group is typed', async () => {
    renderPalette()
    await type('spending')
    // The group name rides in each row's keywords, so one word reaches the
    // whole group rather than only the tab that happens to be called that.
    const rows = await screen.findAllByText(/^Report: /)
    expect(rows.length).toBeGreaterThan(1)
  })

  it('reaches a settings section by its own label', async () => {
    renderPalette()
    await type('simplefin')
    await userEvent.click(await screen.findByText('Settings: SimpleFIN'))
    expect(navigate).toHaveBeenCalledWith('/settings#simplefin')
  })

  it('keeps the words the hand-written rows carried', async () => {
    // "Run integrity check" and "Backups" were static rows until a generated
    // one pointed at the same place; their keywords moved onto the section.
    renderPalette()
    await type('audit')
    expect(await screen.findByText('Settings: Data Integrity')).toBeInTheDocument()
  })

  it('does not offer an admin-only section to someone who is not an admin', async () => {
    renderPalette()
    await type('users')
    await waitFor(() => expect(screen.queryByText('Settings: Users')).not.toBeInTheDocument())
  })

  it('offers it to an admin', async () => {
    currentUser.mockReturnValue({ data: { id: 'u1', email: 'a@b.c', is_admin: true } })
    renderPalette()
    await type('users')
    expect(await screen.findByText('Settings: Users')).toBeInTheDocument()
  })

  it('does not offer a guide tab that preferences have switched off', async () => {
    guideOverview.mockReturnValue({
      data: { preferences: { personalization: true, checkup: true, wishlist: false } },
    })
    renderPalette()
    await type('wishlist')
    await waitFor(() => expect(screen.queryByText('Guide: Wishlist')).not.toBeInTheDocument())
  })

  it('stays quiet until something is typed', async () => {
    // Opening onto 40-odd generated rows would bury the twenty commands the
    // palette exists to offer.
    renderPalette()
    expect(screen.queryByText(/^Report: /)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Settings: /)).not.toBeInTheDocument()
  })
})

describe('CommandPalette glossary', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    navigate.mockClear()
    apiGet.mockReset()
    apiGet.mockResolvedValue({ data: { transactions: [], total_count: 0, total_amount: '0' } })
    useAppStore.setState({ currentBudgetId: 'b1' })
    useUIStore.setState({ isPaletteOpen: true })
    currentUser.mockReturnValue({ data: { id: 'u1', email: 'a@b.c', is_admin: false } })
    guideOverview.mockReturnValue({
      data: { preferences: { personalization: true, checkup: true, wishlist: true } },
    })
  })

  it('answers an alias without anyone pressing Enter', async () => {
    renderPalette()
    await type('tba')
    expect(await screen.findByText('To Be Assigned')).toBeInTheDocument()
    // The definition is the answer, so it is on the row.
    expect(
      await screen.findByText('Money you have received but have not yet given a job.')
    ).toBeInTheDocument()
  })

  it('finds the same term by a phrase alias', async () => {
    renderPalette()
    await type('ready to assign')
    expect(await screen.findByText('To Be Assigned')).toBeInTheDocument()
  })

  it('deep-links one definition', async () => {
    renderPalette()
    await type('tba')
    await userEvent.click(await screen.findByText('To Be Assigned'))
    expect(navigate).toHaveBeenCalledWith('/guide?tab=glossary&term=to-be-assigned')
  })

  it('does not open onto 35 definitions', async () => {
    renderPalette()
    expect(screen.queryByText('To Be Assigned')).not.toBeInTheDocument()
  })
})
