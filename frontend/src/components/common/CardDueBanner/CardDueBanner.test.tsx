/**
 * The app-wide card-bill banner: one line per card whose bill is due or past
 * due, a link to the card, and a Dismiss that the household shares.
 *
 * The rule is `reminderForCard`'s (utils/paymentDue.ts, tested there); these
 * pin what the banner adds — which lines it draws, what they say, and that a
 * dismissal hides exactly the reminder it names.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CardDueDismissal } from '../../../api/cardDueDismissals'
import type { CardDueReminder } from '../../../utils/paymentDue'
import { bannerLines, isDismissed } from './bannerLines'

interface LiabilityRow {
  linked_account_id: string | null
  current_balance: number
  last_payment_date: string | null
  payment_due_kind: 'day_of_month' | 'cycle_days'
  payment_due_day: number | null
  payment_due_cycle_days: number | null
  payment_due_anchor: string | null
}
interface AccountRow {
  id: string
  name: string
  on_budget: boolean
  classification: 'asset' | 'liability'
  budget_start_date: string | null
  created_at: string
}

const data = vi.hoisted(() => ({
  liabilities: [] as LiabilityRow[],
  accounts: [] as AccountRow[],
  dismissals: [] as CardDueDismissal[],
  mutate: vi.fn(),
}))
vi.mock('../../../api/liabilities', () => ({
  useLiabilities: () => ({ data: data.liabilities }),
}))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: data.accounts }) }))
vi.mock('../../../api/cardDueDismissals', () => ({
  useCardDueDismissals: () => ({ data: data.dismissals }),
  useDismissCardDue: () => ({ mutate: data.mutate, isPending: false }),
}))

import { CardDueBanner } from './CardDueBanner'
import { useAppStore } from '../../../stores/appStore'

/** Due on the 17th, owing $412; last paid 10 Aug, so September is unpaid. */
function liability(over: Partial<LiabilityRow> = {}): LiabilityRow {
  return {
    linked_account_id: 'visa',
    current_balance: 412,
    last_payment_date: '2026-08-10',
    payment_due_kind: 'day_of_month',
    payment_due_day: 17,
    payment_due_cycle_days: null,
    payment_due_anchor: null,
    ...over,
  }
}

function account(over: Partial<AccountRow> = {}): AccountRow {
  return {
    id: 'visa',
    name: 'Sapphire Visa',
    on_budget: true,
    classification: 'liability',
    budget_start_date: null,
    created_at: '2026-01-05T15:00:00Z',
    ...over,
  }
}

function show() {
  return render(
    <MemoryRouter>
      <CardDueBanner />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 8, 13, 12, 0, 0)) // Sunday 13 Sep 2026
  useAppStore.setState({ currentBudgetId: 'b1' })
  data.liabilities = [liability()]
  data.accounts = [account()]
  data.dismissals = []
  data.mutate.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('the banner', () => {
  it('says which card, how soon, and what it owes', () => {
    show()

    const line = screen.getByRole('listitem')
    expect(line).toHaveTextContent('Sapphire Visa is due in 4 days (Sep 17) · $412.00 owed')
    expect(screen.getByRole('link', { name: 'Sapphire Visa' })).toHaveAttribute(
      'href',
      '/accounts/visa'
    )
  })

  it('says past due in the negative colour, and what the claim rests on', () => {
    // Due on the 3rd, nothing paid since 20 Jul: 3 Sep went by unpaid.
    data.liabilities = [liability({ payment_due_day: 3, last_payment_date: '2026-07-20' })]
    show()

    const line = screen.getByRole('listitem')
    expect(line).toHaveClass('card-due-banner__line--past-due')
    expect(line).toHaveTextContent(
      'Sapphire Visa is past due since Sep 3 · $412.00 owed · No payment seen since Aug 3'
    )
  })

  it('draws nothing when no bill needs saying', () => {
    data.liabilities = [liability({ last_payment_date: '2026-09-01' })]
    const { container } = show()

    expect(container).toBeEmptyDOMElement()
  })

  it('dismisses exactly the reminder on its line', () => {
    show()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss the reminder for Sapphire Visa' }))

    expect(data.mutate).toHaveBeenCalledExactlyOnceWith({
      accountId: 'visa',
      reminder: { state: 'due', dueDate: '2026-09-17', days: 4, paidAfter: '2026-08-17' },
    })
  })

  it('hides once the dismissal is on file', () => {
    data.dismissals = [{ account_id: 'visa', due_date: '2026-09-17', state: 'due' }]
    const { container } = show()

    expect(container).toBeEmptyDOMElement()
  })

  it('comes back as past due after a "due" was dismissed and nothing was paid', () => {
    data.dismissals = [{ account_id: 'visa', due_date: '2026-09-17', state: 'due' }]
    vi.setSystemTime(new Date(2026, 8, 18, 12, 0, 0))
    show()

    expect(screen.getByRole('listitem')).toHaveTextContent('past due since Sep 17')
  })
})

describe('bannerLines', () => {
  const today = '2026-09-13'

  it('puts past due first, then the soonest', () => {
    const lines = bannerLines(
      [
        liability({ linked_account_id: 'a', payment_due_day: 19 }),
        liability({ linked_account_id: 'b', payment_due_day: 15 }),
        liability({ linked_account_id: 'c', payment_due_day: 3, last_payment_date: '2026-07-20' }),
      ],
      [
        account({ id: 'a', name: 'Thistledown Card' }),
        account({ id: 'b', name: 'Harborstone Card' }),
        account({ id: 'c', name: 'Sapphire Visa' }),
      ],
      [],
      today
    )
    expect(lines.map((l) => l.name)).toEqual([
      'Sapphire Visa',
      'Harborstone Card',
      'Thistledown Card',
    ])
  })

  it('skips a debt whose account is not an on-budget card', () => {
    // Its payments are never served, so every due date would read missed.
    expect(bannerLines([liability()], [account({ on_budget: false })], [], today)).toEqual([])
    expect(bannerLines([liability({ linked_account_id: null })], [account()], [], today)).toEqual(
      []
    )
  })
})

describe('isDismissed', () => {
  const reminder: CardDueReminder = {
    state: 'due',
    dueDate: '2026-09-17',
    days: 4,
    paidAfter: '2026-08-17',
  }
  const on = (d: Partial<CardDueDismissal>) =>
    isDismissed(
      [{ account_id: 'visa', due_date: '2026-09-17', state: 'due', ...d }],
      'visa',
      reminder
    )

  it('matches card, date and state together', () => {
    expect(on({})).toBe(true)
    // A dismissed "due" does not hide a "past due" for the same date…
    expect(on({ state: 'past_due' })).toBe(false)
    // …one date never silences the next…
    expect(on({ due_date: '2026-08-17' })).toBe(false)
    // …and one card never silences another.
    expect(on({ account_id: 'amex' })).toBe(false)
  })
})
