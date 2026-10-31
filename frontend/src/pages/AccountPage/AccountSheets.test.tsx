import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AccountNoticesSheet } from './AccountNoticesSheet'
import { AccountToolsSheet } from './AccountToolsSheet'
import { accountNotices } from './accountNotices'
import { registerToggles } from '../../components/transactions/TransactionTable/registerToggles'

const money = (n: number) => `$${n.toFixed(2)}`

beforeEach(async () => {
  // Every test opens a sheet with a history entry; drain the previous one's
  // deferred history.back() or every other test opens onto a closed sheet.
  window.matchMedia ??= (() => ({ matches: false })) as unknown as typeof window.matchMedia
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
})

const account = {
  name: 'Checking',
  balance: 6193.41,
  cleared_balance: 5588.61,
  uncleared_balance: 604.8,
  pending_balance: -8.41,
  on_budget: true,
  last_reconciled_at: null,
  budget_start_date: null,
}

function renderTools(over: Partial<Parameters<typeof AccountToolsSheet>[0]> = {}) {
  const toggleState = {
    showSplitLines: false,
    setShowSplitLines: vi.fn(),
    showRunningBalance: false,
    setShowRunningBalance: vi.fn(),
  }
  const props = {
    open: true,
    onClose: vi.fn(),
    account,
    isConnected: true,
    formatMoney: money,
    formatDate: (d: string) => d,
    drift: null,
    terms: null,
    onShowUnreconciled: vi.fn(),
    onSync: vi.fn(),
    syncing: false,
    onImport: vi.fn(),
    onScanDuplicates: vi.fn(),
    scanning: false,
    onEdit: vi.fn(),
    onReconcile: null,
    toggles: registerToggles(toggleState, false),
    ...over,
  }
  render(<AccountToolsSheet {...props} />)
  return { ...props, toggleState }
}

describe('AccountToolsSheet', () => {
  it('states the balances, the pending money and the account’s facts', () => {
    renderTools()
    expect(screen.getByText('$5588.61')).toBeInTheDocument()
    expect(screen.getByText('$604.80')).toBeInTheDocument()
    expect(screen.getByText('$6193.41')).toBeInTheDocument()
    expect(screen.getByText(/pending — not in the balances/)).toBeInTheDocument()
    expect(screen.getByText('Connected')).toBeInTheDocument()
    expect(screen.getByText('Never reconciled')).toBeInTheDocument()
  })

  it('closes before it runs an action — each opens a dialog of its own', () => {
    const props = renderTools()
    fireEvent.click(screen.getByRole('button', { name: 'Import a CSV' }))
    expect(props.onClose).toHaveBeenCalled()
    expect(props.onImport).toHaveBeenCalledOnce()
  })

  it('offers Sync only on a connected account', () => {
    renderTools({ onSync: null, isConnected: false })
    expect(screen.queryByRole('button', { name: 'Sync now' })).toBeNull()
    expect(screen.queryByText('Connected')).toBeNull()
  })

  // On a card or loan the header row's button is the payment, so Reconcile
  // has to be somewhere — here.
  it('offers Reconcile only where the header row does not', () => {
    renderTools({ onReconcile: vi.fn() })
    expect(screen.getByRole('button', { name: 'Reconcile' })).toBeInTheDocument()
  })

  // Moved here from beside the search box, which on a phone keeps its row.
  it.each([
    ['split lines', 'setShowSplitLines'],
    ['running balance', 'setShowRunningBalance'],
  ] as const)('toggles %s in place, without closing', (noun, setter) => {
    const props = renderTools()
    const toggle = screen.getByRole('button', { name: `Show ${noun}` })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(toggle)
    expect(props.toggleState[setter]).toHaveBeenCalledWith(true)
    expect(props.onClose).not.toHaveBeenCalled()
  })

  it('shows a debt account’s terms', () => {
    renderTools({ terms: <div>APR 6.25%</div> })
    expect(screen.getByRole('region', { name: 'Terms' })).toHaveTextContent('APR 6.25%')
  })
})

describe('AccountNoticesSheet', () => {
  const notices = accountNotices({
    review: {
      unapproved_only: 12,
      uncategorized_only: 2,
      both: 1,
      total: 15,
      unapproved: 13,
      uncategorized: 3,
    },
    duplicates: 2,
    drift: { tone: 'fault', text: 'Bank reports $5,570.00 — $18.60 more than cleared here.' },
  })

  it('lists each kind with the way to deal with it', () => {
    const onClose = vi.fn()
    const onReviewDuplicates = vi.fn()
    const onViewReview = vi.fn()
    render(
      <AccountNoticesSheet
        open
        onClose={onClose}
        notices={notices}
        onReviewDuplicates={onReviewDuplicates}
        onViewReview={onViewReview}
      />
    )
    expect(screen.getByText('2 possible duplicates')).toBeInTheDocument()
    expect(screen.getByText(/Bank reports \$5,570\.00/)).toBeInTheDocument()
    expect(screen.getByText('13 to approve · 3 to categorize')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Review' }))
    expect(onReviewDuplicates).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'View' }))
    expect(onViewReview).toHaveBeenCalledOnce()
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('says so when the list empties while it is open', () => {
    render(
      <AccountNoticesSheet
        open
        onClose={vi.fn()}
        notices={[]}
        onReviewDuplicates={vi.fn()}
        onViewReview={vi.fn()}
      />
    )
    expect(screen.getByText('Nothing is waiting.')).toBeInTheDocument()
  })
})
