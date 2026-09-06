/**
 * A peek opened from inside a dialog has to land on top of it.
 *
 * The report: clicking an envelope in "Overspending on cards" appeared to do
 * nothing, and closing the dialog "closed it all". Both were one bug. The
 * peek drew its own `position: fixed` overlay instead of using `Modal`, so it
 * rendered inline in the page rather than portalling to `document.body`. At
 * the same z-index as the dialog above it, and earlier in the DOM, it painted
 * behind — invisible, and unreachable without dismissing its parent.
 *
 * These pin the two properties that fix it: the peek portals to the body, and
 * it is the newest overlay there.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api/transactions', () => ({
  useTransactionsPeek: () => ({ data: { transactions: [], total_count: 0 }, isPending: false }),
  usePayees: () => ({ data: [] }),
}))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: [] }) }))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

import { Dialog } from '../../common/Dialog/Dialog'
import { TransactionsPeekModal } from './TransactionsPeekModal'

const SCOPE = { kind: 'category', categoryId: 'c1', categoryName: 'Dining' } as const

beforeEach(() => {
  document.body.innerHTML = ''
})

function overlays() {
  return Array.from(document.body.querySelectorAll('.overlay'))
}

describe('a peek raised from inside a dialog', () => {
  it('portals to the body rather than rendering inline', () => {
    const { container } = render(
      <TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />
    )
    // Nothing in the caller's own subtree: an inline overlay is exactly what
    // put this behind the dialog that opened it.
    expect(container.querySelector('.category-txns')).toBeNull()
    expect(document.body.querySelector('.category-txns')).not.toBeNull()
  })

  it('is the last overlay in the body, so it paints over the dialog', () => {
    render(
      <>
        <Dialog title="Overspending on cards" onClose={vi.fn()} historyKey="on-cards">
          <p>rode onto the card</p>
        </Dialog>
        <TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />
      </>
    )
    const found = overlays()
    expect(found.length).toBe(2)
    // Same --z-overlay by design; DOM order is what decides, and the peek
    // opened second so it must be second.
    expect(found[found.length - 1].querySelector('.category-txns')).not.toBeNull()
  })

  it('leaves the dialog behind it mounted when it closes', () => {
    const onClose = vi.fn()
    const { rerender } = render(
      <>
        <Dialog title="Overspending on cards" onClose={vi.fn()} historyKey="on-cards">
          <p>rode onto the card</p>
        </Dialog>
        <TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={onClose} />
      </>
    )
    rerender(
      <>
        <Dialog title="Overspending on cards" onClose={vi.fn()} historyKey="on-cards">
          <p>rode onto the card</p>
        </Dialog>
      </>
    )
    expect(document.body.querySelector('.category-txns')).toBeNull()
    expect(screen.getByText('rode onto the card')).toBeInTheDocument()
  })
})
