import { describe, it, expect } from 'vitest'
import {
  reserveNote,
  debtMovement,
  rideMonths,
  otherCredits,
  emptyLegsNote,
  pendingNote,
} from './cardRow'
import type { CardStatus } from '../../../types'

const money = (n: number) => `$${n.toFixed(2)}`

/** Amounts are invented and rescaled from the budget that raised these cases —
 *  the ratios carry the lesson, the digits are nobody's. */
function card(over: Partial<CardStatus> = {}): CardStatus {
  return {
    account_id: 'a1',
    name: 'Sapphire Visa',
    category_id: 'c1',
    balance: -100,
    set_aside: 100,
    uncovered: 0,
    is_closed: false,
    overspent_this_month: 0,
    reserve_discrepancy: 0,
    assigned: 0,
    reserved: 100,
    released: 0,
    residual: 0,
    payments: 0,
    riding: 0,
    over_reserved: 0,
    short_reserved: 0,
    card_credit: 0,
    charged_this_month: 0,
    inflows_this_month: 0,
    paid_this_month: 0,
    debt_change_this_month: 0,
    pending_this_month: 0,
    rode_by_month: [],
    ...over,
  }
}

describe('reserveNote', () => {
  it('says nothing about a card whose reserve matches what it owes', () => {
    expect(reserveNote(card(), money)).toBeNull()
  })

  it('calls it a credit balance only when the card owes nothing', () => {
    const note = reserveNote(card({ set_aside: -50, balance: 50, card_credit: 50 }), money)
    expect(note?.label).toBe('credit balance')
  })

  it('never says overpaid on a card that still owes', () => {
    // The defect, in one assertion. The row printed "overpaid" beside a
    // negative reserve while the column to its right showed the whole balance
    // as uncovered.
    const note = reserveNote(
      card({
        balance: -5400,
        set_aside: -220,
        short_reserved: 220,
        uncovered: 5400,
        payments: 220,
      }),
      money
    )
    expect(note?.label).toBe('ahead of budget')
    expect(note?.title).not.toMatch(/overpaid/i)
  })

  it('names the assignment as the remedy for a plain paydown', () => {
    const note = reserveNote(
      card({ balance: -5400, set_aside: -220, short_reserved: 220, payments: 220 }),
      money
    )
    expect(note?.title).toContain('Assign $220.00')
    expect(note?.title).toContain('already left your account')
  })

  it('names back-funding when a month boundary caused it', () => {
    const note = reserveNote(
      card({ balance: -500, set_aside: -300, short_reserved: 300, riding: 300, payments: 500 }),
      money
    )
    expect(note?.title).toContain("Fund that month's envelope")
  })

  it('names the inflow when residual alone accounts for the shortfall', () => {
    // The below-zero card: a third party pays part of the bill, filed to a
    // category that never charged this card. Takes priority over `riding`
    // because it explains the whole number on its own.
    const note = reserveNote(
      card({
        balance: -5400,
        set_aside: -220,
        short_reserved: 220,
        residual: 4120,
        riding: 40,
      }),
      money
    )
    expect(note?.title).toContain('beyond anything an envelope charged to it')
  })

  it('reports an over-reserve the discrepancy check is silent about', () => {
    // reserve_discrepancy is 0 here on purpose: T1 excuses an over-reserve
    // explained by assignments, so a row keyed on it says nothing about the
    // card that has drifted furthest.
    const note = reserveNote(
      card({
        balance: -1500,
        set_aside: 7400,
        over_reserved: 5900,
        assigned: 5900,
        reserve_discrepancy: 0,
      }),
      money
    )
    expect(note?.label).toBe('$5900.00 spare')
    expect(note?.title).toContain('Safe to release')
    expect(note?.title).toContain('did leave Ready to Assign')
  })

  it('does not claim assignments caused an over-reserve on a card carrying a ride', () => {
    const note = reserveNote(
      card({ balance: -100, set_aside: 400, over_reserved: 300, assigned: 300, riding: 50 }),
      money
    )
    expect(note?.title).not.toContain('assignments accumulate')
  })
})

describe('debtMovement', () => {
  it('says nothing in a month the balance did not move', () => {
    expect(debtMovement(card(), money)).toBeNull()
  })

  it('reads a rising balance as debt going down', () => {
    // The whole point of the phrasing: a balance moving from -900 to -672 is
    // going UP while the debt goes DOWN, and only one of those is what a
    // person means by "the card got better".
    const note = debtMovement(
      card({ debt_change_this_month: 228, charged_this_month: 412, paid_this_month: 640 }),
      money
    )
    expect(note?.label).toBe('down $228.00')
    expect(note?.title).toContain('$412.00 charged, $640.00 paid')
  })

  it('reads a falling balance as debt going up', () => {
    const note = debtMovement(card({ debt_change_this_month: -412 }), money)
    expect(note?.label).toBe('up $412.00')
  })
})

describe('rideMonths', () => {
  const months = (n: number) =>
    Array.from({ length: n }, (_, i) => ({ month: `2026-0${i + 1}-01`, amount: (i + 1) * 10 }))

  it('orders by size so the month worth back-funding first comes first', () => {
    expect(rideMonths(card({ rode_by_month: months(3) })).shown.map((m) => m.amount)).toEqual([
      30, 20, 10,
    ])
  })

  it('reports how many it left out rather than truncating silently', () => {
    const { shown, elided } = rideMonths(card({ rode_by_month: months(5) }))
    expect(shown).toHaveLength(3)
    expect(elided).toBe(2)
  })

  it('elides nothing when everything fits', () => {
    expect(rideMonths(card({ rode_by_month: months(2) })).elided).toBe(0)
  })

  it('reports nothing retired when the list matches what is still riding', () => {
    expect(rideMonths(card({ rode_by_month: months(3), riding: 60 })).retired).toBe(0)
  })

  it('names what an assignment has already retired', () => {
    // The list is GROSS — the months debt went on — while `riding` is net.
    // Retirement is recorded against the assignment's month, not the month
    // that rode, so without this the panel points at settled months.
    expect(rideMonths(card({ rode_by_month: months(3), riding: 20 })).retired).toBe(40)
  })

  it('never reports a negative retirement', () => {
    expect(rideMonths(card({ rode_by_month: months(1), riding: 999 })).retired).toBe(0)
  })
})

describe('otherCredits', () => {
  it('is zero when everything received was a paired payment', () => {
    // 640 arrived, all of it the transfer from checking: nothing else came.
    expect(otherCredits(card({ inflows_this_month: 640, paid_this_month: 640 }))).toBe(0)
  })

  it('names a payment recorded as a deposit rather than a transfer', () => {
    // 300 arrived with nothing paired against it. Only a transfer spends the
    // reserve, so Ready to pay stood still while the card's debt dropped —
    // one way a card ends up reserving far more than it owes.
    expect(otherCredits(card({ inflows_this_month: 300, paid_this_month: 0 }))).toBe(300)
  })

  it('names a refund beside a real payment', () => {
    expect(otherCredits(card({ inflows_this_month: 130, paid_this_month: 100 }))).toBe(30)
  })

  it('rounds to cents — a difference of two served figures, never a plug', () => {
    // The old computation (debt_change + charged − paid) was algebra over
    // the other terms, so it could not fail to reconcile even when they
    // were wrong. This one can, which is the point.
    expect(otherCredits(card({ inflows_this_month: 0.3, paid_this_month: 0.1 }))).toBe(0.2)
  })
})

describe('emptyLegsNote', () => {
  it('says nothing has moved when the card really is untouched', () => {
    const note = emptyLegsNote(
      card({ balance: 0, charged_this_month: 0, debt_change_this_month: 0 })
    )
    expect(note).toContain('Nothing has moved through this card')
  })

  it('does not claim a card with a balance is untouched', () => {
    // The real shape, rescaled: a card owing money whose every charge is
    // uncategorized, so all five reserve legs are zero. The old copy printed
    // "nothing has moved" directly above "Charged $2,400.00".
    const note = emptyLegsNote(
      card({ balance: -8200, charged_this_month: 2400, debt_change_this_month: 1500 })
    )
    expect(note).not.toContain('Nothing has moved')
    expect(note).toContain('set aside')
  })

  it('does not claim a card that only took a credit is untouched', () => {
    const note = emptyLegsNote(
      card({ balance: 0, charged_this_month: 0, debt_change_this_month: 90 })
    )
    expect(note).not.toContain('Nothing has moved')
  })
})

describe('pendingNote', () => {
  it('says nothing when every row has posted', () => {
    expect(pendingNote(card({ pending_this_month: 0 }), money)).toBeNull()
  })

  it('names the gap between this panel and the register', () => {
    // The panel and the balance both exclude pending; the register does not.
    // A user counting the register found more charges than the panel showed.
    const note = pendingNote(card({ pending_this_month: -65 }), money)
    expect(note).toContain('$65.00')
    expect(note).toContain('charges')
    expect(note).toContain('register')
  })

  it('calls a pending credit a credit', () => {
    const note = pendingNote(card({ pending_this_month: 30 }), money)
    expect(note).toContain('credits')
    expect(note).toContain('$30.00')
  })
})
