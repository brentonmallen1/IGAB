/**
 * The panel's job is to be worth reading. Two properties carry that: it says
 * nothing when there is nothing to say, and a finding you dismiss stays gone.
 *
 * A panel that always shows something is one people learn to scroll past —
 * and then the finding that matters goes past too.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AccountHygienePanel } from './AccountHygienePanel'
import type { HygieneFinding, HygieneReport } from '../../api/accounts'

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

let report: HygieneReport = { findings: [], clean: true }
const repairMutate = vi.hoisted(() =>
  vi.fn(() => Promise.resolve({ linked: 0, ambiguous: 0, remaining: 0 }))
)
const stripMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({ stripped: 0 })))
vi.mock('../../api/accounts', () => ({
  useAccountHygiene: () => ({ data: report }),
  useRepairTransfers: () => ({ mutateAsync: repairMutate, isPending: false }),
  useRepairTrackingCategories: () => ({ mutateAsync: stripMutate, isPending: false }),
}))

const toastSuccess = vi.hoisted(() => vi.fn())
const toastError = vi.hoisted(() => vi.fn())
vi.mock('react-hot-toast', () => ({
  default: { success: toastSuccess, error: toastError },
}))

function finding(over: Partial<HygieneFinding> = {}): HygieneFinding {
  return {
    kind: 'liability_positive_balance',
    title: '3 debt accounts hold a positive balance',
    detail: 'A debt-typed account is subtracted from net worth.',
    action: 'Check the balance.',
    account_ids: [],
    transaction_count: 0,
    ...over,
  }
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AccountHygienePanel budgetId="b1" />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  navigate.mockClear()
  repairMutate.mockClear()
  toastSuccess.mockClear()
  toastError.mockClear()
  report = { findings: [], clean: true }
})

describe('AccountHygienePanel', () => {
  it('renders nothing at all on a clean budget', () => {
    // Not an empty state, not a green tick — nothing. The reward for a tidy
    // budget is that the app stops talking.
    const { container } = renderPanel()
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a finding with what to do about it', () => {
    report = { findings: [finding()], clean: false }
    renderPanel()
    expect(screen.getByText('3 debt accounts hold a positive balance')).toBeInTheDocument()
    expect(screen.getByText('Check the balance.')).toBeInTheDocument()
  })

  it('sends unpaired transfers to the rows they are about', () => {
    // A finding with no way to reach what it describes is just criticism —
    // which is what the import toast was.
    report = {
      findings: [finding({ kind: 'unpaired_transfer_legs', transaction_count: 1117 })],
      clean: false,
    }
    renderPanel()
    screen.getByText(/Show them/).click()
    expect(navigate).toHaveBeenCalledWith('/transactions?q=is:unpaired')
  })

  it('offers no link for a finding that has no list to open', () => {
    report = { findings: [finding()], clean: false }
    renderPanel()
    expect(screen.queryByText(/Show them/)).not.toBeInTheDocument()
  })

  it('drops a dismissed finding and remembers the decision', async () => {
    report = { findings: [finding()], clean: false }
    const { unmount } = renderPanel()
    await userEvent.click(screen.getByLabelText(/Dismiss/))
    expect(screen.queryByText('3 debt accounts hold a positive balance')).not.toBeInTheDocument()

    unmount()
    const { container } = renderPanel()
    expect(container).toBeEmptyDOMElement()
  })

  it('still speaks up about a different kind of problem after a dismissal', () => {
    // Dismissal is per kind, not "be quiet forever". Someone who has decided
    // to live with dormant accounts still needs to hear about a mistyped one.
    localStorage.setItem('igab.hygiene.dismissed', JSON.stringify(['dormant_open_account']))
    report = {
      findings: [finding({ kind: 'dormant_open_account', title: 'quiet' }), finding()],
      clean: false,
    }
    renderPanel()
    expect(screen.queryByText('quiet')).not.toBeInTheDocument()
    expect(screen.getByText('3 debt accounts hold a positive balance')).toBeInTheDocument()
  })

  it('survives storage that throws, as a private window does', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    report = { findings: [finding()], clean: false }
    expect(() => renderPanel()).not.toThrow()
    expect(screen.getByText('3 debt accounts hold a positive balance')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('offers to match unpaired transfers up, and says what is left over', async () => {
    // The count that made this exist was 1,117. A pass that links most of
    // them and reports only its successes reads as "done" when it is not.
    repairMutate.mockResolvedValueOnce({ linked: 900, ambiguous: 200, remaining: 17 })
    report = {
      findings: [finding({ kind: 'unpaired_transfer_legs', title: '1,117 transfers' })],
      clean: false,
    }
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: /Match them up/ }))
    expect(repairMutate).toHaveBeenCalled()
    expect(toastSuccess).toHaveBeenCalledWith(
      expect.stringContaining('Linked 900 transfers'),
      expect.anything()
    )
    expect(toastSuccess.mock.calls[0][0]).toContain('200 need you to choose')
    expect(toastSuccess.mock.calls[0][0]).toContain('17 have no other side')
  })

  it('offers no matching button for other kinds of finding', () => {
    report = { findings: [finding()], clean: false }
    renderPanel()
    expect(screen.queryByRole('button', { name: /Match them up/ })).not.toBeInTheDocument()
  })
})
