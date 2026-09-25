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
import type { FindingItem, HygieneFinding, HygieneReport } from '../../api/accounts'

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
const linkMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({ linked: 2, skipped: 0 })))
vi.mock('../../api/accounts', () => ({
  useAccountHygiene: () => ({ data: report }),
  useRepairTransfers: () => ({ mutateAsync: repairMutate, isPending: false }),
  useRepairTrackingCategories: () => ({ mutateAsync: stripMutate, isPending: false }),
  useLinkCardPayments: () => ({ mutateAsync: linkMutate, isPending: false }),
}))
const confirmAsync = vi.hoisted(() => vi.fn(() => Promise.resolve(true)))
vi.mock('../../stores/confirmStore', () => ({ confirmAsync }))

const toastSuccess = vi.hoisted(() => vi.fn())
const toastError = vi.hoisted(() => vi.fn())
vi.mock('react-hot-toast', () => ({
  default: { success: toastSuccess, error: toastError },
}))

function finding(over: Partial<HygieneFinding> = {}): HygieneFinding {
  return {
    kind: 'liability_positive_balance',
    title: '3 debt accounts hold a positive balance',
    summary: 'A debt account holding money is usually something you own.',
    action: 'Check the balance.',
    items: [],
    why: 'Debt accounts are subtracted from net worth.',
    account_ids: [],
    asset_ids: [],
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
    expect(screen.getByText(/Check the balance\./)).toBeInTheDocument()
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

  it("lists what a finding is about, with amounts in the budget's own format", () => {
    // The server used to type figures into its sentences — "58.6800" and
    // "-100.0000" reached the screen, and a list of seven arrived as prose.
    report = {
      findings: [
        finding({
          kind: 'card_debt_predates_budget',
          title: '1 card carrying debt from before the budget',
          items: [
            item({
              label: 'Sapphire Visa',
              amount: '-58.6800',
              note: 'charged since March 2026, nothing set aside until June 2026',
              account_id: 'card-1',
            }),
          ],
        }),
      ],
      clean: false,
    }
    renderPanel()
    expect(screen.queryByText(/58\.6800/)).not.toBeInTheDocument()
    expect(screen.getByText(/58\.68/)).toBeInTheDocument()
    expect(
      screen.getByText(/charged since March 2026, nothing set aside until June 2026/)
    ).toBeInTheDocument()

    screen.getByRole('button', { name: 'Sapphire Visa' }).click()
    expect(navigate).toHaveBeenCalledWith('/accounts/card-1')
  })

  it('folds the reasoning away, and a long list behind "show more"', async () => {
    report = {
      findings: [
        finding({
          items: Array.from({ length: 7 }, (_, i) => item({ label: `Account ${i + 1}` })),
        }),
      ],
      clean: false,
    }
    renderPanel()
    // In a closed <details>: present for whoever opens it, not in the way.
    expect(
      screen.getByText('Debt accounts are subtracted from net worth.').closest('details')
    ).not.toHaveAttribute('open')
    expect(screen.queryByText('Account 6')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show 2 more' }))
    expect(screen.getByText('Account 7')).toBeInTheDocument()
  })

  it('links every unlinked card payment at once, after saying what it does', async () => {
    report = {
      findings: [
        finding({
          kind: 'unlinked_card_payments',
          title: '2 card payments not linked',
          items: [
            item({ label: 'Sapphire Visa', amount: '460.00', transaction_ids: ['o1', 'i1'] }),
            item({ label: 'Sapphire Visa', amount: '125.00', transaction_ids: ['o2', 'i2'] }),
          ],
        }),
      ],
      clean: false,
    }
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /Link all 2/ }))

    expect(confirmAsync).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('Set aside falls') })
    )
    expect(linkMutate).toHaveBeenCalledWith([
      ['o1', 'i1'],
      ['o2', 'i2'],
    ])
    expect(toastSuccess).toHaveBeenCalledWith('Linked 2 payments.', expect.anything())
  })

  it('links nothing when the confirm is declined', async () => {
    confirmAsync.mockResolvedValueOnce(false)
    linkMutate.mockClear()
    report = {
      findings: [
        finding({
          kind: 'unlinked_card_payments',
          items: [item({ label: 'Sapphire Visa', transaction_ids: ['o1', 'i1'] })],
        }),
      ],
      clean: false,
    }
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /Link all 1/ }))
    expect(linkMutate).not.toHaveBeenCalled()
  })
})

function item(over: Partial<FindingItem> = {}): FindingItem {
  return {
    label: 'Item',
    amount: null,
    month: null,
    day: null,
    note: null,
    account_id: null,
    transaction_id: null,
    transaction_ids: [],
    ...over,
  }
}
