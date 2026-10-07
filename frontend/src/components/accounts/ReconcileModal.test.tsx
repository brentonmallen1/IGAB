/**
 * The opening question of a reconciliation, in the shared dialog styles.
 *
 * Continue was disabled until something was typed, and something that did not
 * parse ("abc") did nothing at all — no error, no progress. It now stays
 * enabled and says what it needs, like every other dialog's primary button.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReconcileModal } from './ReconcileModal'

const ui = vi.hoisted(() => ({
  setReconcileStatementBalance: vi.fn(),
  cancelReconciliation: vi.fn(),
}))
vi.mock('../../stores/uiStore', () => ({ useUIStore: () => ui }))
let inReviewCount = 0
vi.mock('../../api/reconciliation', () => ({
  useReconciliationStatus: () => ({
    data: {
      cleared_balance: '1250.00',
      uncleared_count: 0,
      pending_count: 0,
      in_review_count: inReviewCount,
    },
  }),
}))

const onReviewDuplicates = vi.fn()

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  ui.setReconcileStatementBalance.mockClear()
  ui.cancelReconciliation.mockClear()
  onReviewDuplicates.mockClear()
  inReviewCount = 0
})

function renderModal() {
  render(
    <ReconcileModal
      accountId="a1"
      accountName="Cascade Point HYSA"
      onReviewDuplicates={onReviewDuplicates}
    />
  )
}

async function answerNo() {
  renderModal()
  await userEvent.click(screen.getByRole('button', { name: 'No' }))
}

describe('ReconcileModal', () => {
  it('takes the cleared balance on Yes', async () => {
    renderModal()
    const yes = screen.getByRole('button', { name: 'Yes' })
    expect(yes).toHaveClass('dialog-btn', 'dialog-btn--primary')
    await userEvent.click(yes)
    expect(ui.setReconcileStatementBalance).toHaveBeenCalledWith(1250)
  })

  it('asks for the bank balance in a labelled shared field', async () => {
    await answerNo()
    const input = screen.getByLabelText('What does your bank say?')
    expect(input.closest('form')).toHaveClass('dialog-form')
    expect(input.closest('.dialog-form__field')).not.toBeNull()
  })

  it('keeps Continue enabled while empty and says what it needs', async () => {
    await answerNo()
    const cont = screen.getByRole('button', { name: 'Continue' })
    expect(cont).toBeEnabled()
    await userEvent.click(cont)
    expect(screen.getByText('Enter the balance your bank shows')).toHaveClass('dialog-form__error')
    expect(ui.setReconcileStatementBalance).not.toHaveBeenCalled()
  })

  it('refuses text that is not an amount rather than doing nothing', async () => {
    await answerNo()
    await userEvent.type(screen.getByLabelText('What does your bank say?'), 'abc{Enter}')
    expect(screen.getByText('Enter the balance your bank shows')).toBeInTheDocument()
    expect(ui.setReconcileStatementBalance).not.toHaveBeenCalled()
  })

  it.each([
    ['1,180.40', 1180.4],
    ['-42.10', -42.1],
  ])('submits %s on Enter as %s', async (typed, expected) => {
    await answerNo()
    await userEvent.type(screen.getByLabelText('What does your bank say?'), `${typed}{Enter}`)
    expect(ui.setReconcileStatementBalance).toHaveBeenCalledWith(expected)
  })
})

/**
 * A sync that queues a possible duplicate writes the bank's copy cleared
 * beside the person's own cleared row, so the balance this modal asks about
 * counts it twice. Reconciling to the bank anyway wrote an adjustment the
 * merge then made permanently wrong; the server now refuses, and the modal
 * says why before the question is answered.
 */
describe('ReconcileModal with duplicates waiting in review', () => {
  it('says nothing about review when none are waiting', () => {
    renderModal()
    expect(screen.queryByText(/waiting in review/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /review/i })).not.toBeInTheDocument()
  })

  it('names one waiting duplicate and opens the review', async () => {
    inReviewCount = 1
    renderModal()
    expect(
      screen.getByText(/1 possible duplicate is waiting in review, so this balance counts it twice/)
    ).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Review it' }))
    expect(onReviewDuplicates).toHaveBeenCalledTimes(1)
  })

  it('counts several in the plural', () => {
    inReviewCount = 3
    renderModal()
    expect(
      screen.getByText(/3 possible duplicates are waiting in review, so this balance counts them/)
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review them' })).toBeInTheDocument()
  })
})
