import { describe, it, expect } from 'vitest'
import { dueInPhrase } from '../../../utils/paymentDue'
import {
  reserveLegs,
  debtMovementLabel,
  debtMovementWord,
  driftSentence,
  dueHeaderNote,
  rideMonths,
  otherCredits,
  emptyLegsNote,
  pendingNote,
  setAsideLabel,
  setAsideShown,
  stateSentence,
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
    imported_riding: 0,
    covered: 0,
    opening: 0,
    over_reserved: 0,
    short_reserved: 0,
    card_credit: 0,
    set_aside_state: 'funded',
    charged_this_month: 0,
    inflows_this_month: 0,
    paid_this_month: 0,
    debt_change_this_month: 0,
    pending_this_month: 0,
    rode_by_month: [],
    overspent_by_category: [],
    ...over,
  }
}

describe('what the Set aside column prints', () => {
  it('prints the figure on a card that is holding money', () => {
    expect(setAsideShown(card({ set_aside: 240 }))).toBe(240)
  })

  it('never prints a negative, whichever of the four causes produced it', () => {
    for (const state of [
      'settled_by_others',
      'refund_outran_envelope',
      'settled_elsewhere',
      'ride_unfunded',
      'paid_ahead',
    ] as const) {
      expect(setAsideShown(card({ set_aside: -300, set_aside_state: state })), state).toBe(0)
    }
  })

  it('moves the magnitude to a named line instead of dropping it', () => {
    // Showing $0.00 and saying nothing else would hide a real figure. The
    // distance is a fact and stays on screen; what it MEANS is the sentence.
    const label = setAsideLabel(
      card({ set_aside: -300, short_reserved: 300, set_aside_state: 'paid_ahead' }),
      money
    )
    expect(label).toBe('$300.00 below zero')
  })

  it('gives the four negatives no noun of their own', () => {
    // They want opposite responses — nothing to do, re-file an inflow,
    // back-fund a month, assign to the card — and one word for all four is
    // what made this column unreadable.
    const labels = (
      ['settled_by_others', 'refund_outran_envelope', 'settled_elsewhere', 'paid_ahead'] as const
    ).map((s) =>
      setAsideLabel(card({ set_aside: -300, short_reserved: 300, set_aside_state: s }), money)
    )
    expect(new Set(labels).size).toBe(1)
  })

  it('says nothing beside a card with nothing to say', () => {
    expect(setAsideLabel(card(), money)).toBeNull()
    expect(stateSentence(card(), money)).toBeNull()
  })
})

describe('the sentence under the row', () => {
  it('calls it a credit balance only when the card owes nothing', () => {
    const card_ = card({
      set_aside: -50,
      balance: 50,
      card_credit: 50,
      set_aside_state: 'card_holds_it',
    })
    expect(setAsideLabel(card_, money)).toBe('credit balance')
    expect(stateSentence(card_, money)?.sentence).toContain('owes nothing')
  })

  it('names what came back, not what was left of it', () => {
    // The bug this test exists for: the row read "$100 came back" beside an
    // envelope plainly showing $500. $100 was the residue after the month's
    // reservations and payments; $500 is what actually arrived.
    const said = stateSentence(
      card({
        set_aside: -100,
        short_reserved: 100,
        residual: 500,
        set_aside_state: 'refund_outran_envelope',
      }),
      money
    )
    expect(said?.sentence).toContain('$500.00')
    expect(said?.sentence).not.toContain('$100.00')
  })

  it('says a refund the envelope kept is spendable money that never arrived', () => {
    const said = stateSentence(
      card({
        set_aside: -100,
        short_reserved: 100,
        residual: 500,
        set_aside_state: 'refund_outran_envelope',
      }),
      money
    )
    expect(said?.sentence).toMatch(/credit on this card/)
    // Describe, don't prescribe: nobody knows which envelope should give it
    // back, or whether it should.
    expect(said?.action).toBeUndefined()
  })

  it('tells a settle-up that nothing is wrong, in as many words', () => {
    const said = stateSentence(
      card({
        set_aside: -200,
        short_reserved: 200,
        residual: 400,
        set_aside_state: 'settled_by_others',
      }),
      money
    )
    expect(said?.sentence).toContain('$400.00')
    expect(said?.action).toBe('Nothing to do.')
  })

  it('promises that funding a month works only where the ride is this card alone', () => {
    // F8. The old copy offered this on every riding card, and on a shared
    // shortfall funding the envelope moves a DIFFERENT card.
    const alone = stateSentence(
      card({ set_aside: -300, short_reserved: 300, riding: 200, set_aside_state: 'ride_unfunded' }),
      money
    )
    expect(alone?.action).toMatch(/Raise that month's assignment/)

    const shared = stateSentence(
      card({
        set_aside: -60,
        short_reserved: 60,
        riding: 300,
        set_aside_state: 'settled_elsewhere',
      }),
      money
    )
    expect(shared?.action).not.toMatch(/envelope/)
    expect(shared?.sentence).toMatch(/another card/)
  })

  it('offers the assignment on a plain overpayment, and quotes the amount', () => {
    const said = stateSentence(
      card({ set_aside: -300, short_reserved: 300, set_aside_state: 'paid_ahead' }),
      money
    )
    expect(said?.sentence).toContain('$300.00')
    expect(said?.action).toContain('Ready to Assign')
  })

  it('calls a surplus spare and says where releasing it goes', () => {
    const card_ = card({
      set_aside: 1250,
      balance: -50,
      over_reserved: 1200,
      set_aside_state: 'surplus',
    })
    expect(setAsideLabel(card_, money)).toBe('$1200.00 spare')
    expect(stateSentence(card_, money)?.action).toContain('Ready to Assign')
  })

  it('does not branch on a cause the server did not decide', () => {
    // Every figure in the copy is a served leg. The old note compared a
    // LIFETIME residual against a CURRENT shortfall to pick its wording,
    // which is a guess dressed as arithmetic.
    for (const state of [
      'surplus',
      'card_holds_it',
      'settled_by_others',
      'refund_outran_envelope',
      'settled_elsewhere',
      'ride_unfunded',
      'paid_ahead',
    ] as const) {
      expect(stateSentence(card({ set_aside_state: state }), money), state).not.toBeNull()
    }
  })
})

describe('driftSentence', () => {
  it('is silent when the identity closes', () => {
    expect(driftSentence(card(), money)).toBeNull()
  })

  it('is a sentence, not a tooltip, when it does not', () => {
    // It was a `title`, which an installed iOS PWA never renders.
    expect(driftSentence(card({ reserve_discrepancy: 42 }), money)).toContain('$42.00')
  })
})

describe('debtMovementLabel', () => {
  it('says nothing in a month the balance did not move', () => {
    expect(debtMovementLabel(card(), money)).toBeNull()
  })

  it('reads a rising balance as the debt decreasing', () => {
    // The whole point of the phrasing: a balance moving from -900 to -672 is
    // going UP while the debt goes DOWN, and only one of those is what a
    // person means by "the card got better".
    expect(debtMovementLabel(card({ debt_change_this_month: 228 }), money)).toBe(
      'debt\u00A0decreased $228.00'
    )
  })

  it('reads a falling balance as the debt increasing', () => {
    expect(debtMovementLabel(card({ debt_change_this_month: -412 }), money)).toBe(
      'debt\u00A0increased $412.00'
    )
  })

  // "down $412" beside a balance that grew is the report this wording came
  // from: never a bare direction word, on either side of zero.
  it('never says up or down', () => {
    for (const moved of [228, -412]) {
      expect(debtMovementLabel(card({ debt_change_this_month: moved }), money)).not.toMatch(
        /\b(up|down)\b/
      )
    }
  })

  it('breaks only between the phrase and the figure', () => {
    const label = debtMovementLabel(card({ debt_change_this_month: -412 }), money)
    // One breakable space, and it sits before the amount.
    expect(label?.split(' ')).toHaveLength(2)
  })
})

describe('debtMovementWord', () => {
  it('names the debt, not the balance', () => {
    expect(debtMovementWord(228)).toBe('decreased')
    expect(debtMovementWord(-412)).toBe('increased')
  })

  it('treats an unmoved debt as decreased, so the drawer never says increased at zero', () => {
    expect(debtMovementWord(0)).toBe('decreased')
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

  it('names what an assignment has already retired, from the served leg', () => {
    // The list is GROSS — the months debt went on — while `riding` is net.
    // Retirement is recorded against the assignment's month, not the month
    // that rode, so without this the panel points at settled months. The
    // figure is the served `covered`, never `gross − riding`: a discharging
    // refund lowers `riding` with no assignment at all, and an imported
    // budget's `riding` used to carry opening debt the list never had.
    expect(rideMonths(card({ rode_by_month: months(3), covered: 40 })).retired).toBe(40)
  })

  it('does not infer a retirement the server did not report', () => {
    // 60 rode, 20 still riding, nothing covered: the other 40 was discharged
    // by inflows. The old subtraction called that "covered by assignments".
    expect(rideMonths(card({ rode_by_month: months(3), riding: 20, covered: 0 })).retired).toBe(0)
  })
})

describe('otherCredits', () => {
  it('is zero when everything received was a paired payment', () => {
    // 640 arrived, all of it the transfer from checking: nothing else came.
    expect(otherCredits(card({ inflows_this_month: 640, paid_this_month: 640 }))).toBe(0)
  })

  it('names a payment recorded as a deposit rather than a transfer', () => {
    // 300 arrived with nothing paired against it. Only a transfer spends the
    // reserve, so Set aside stood still while the card's debt dropped —
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

describe('reserveLegs', () => {
  it('names the five terms, in order, with the sign each carries', () => {
    const legs = reserveLegs({
      assigned: 40,
      reserved: 100,
      released: 20,
      residual: 7,
      payments: 5,
      opening: 0,
    })
    expect(legs.map((l) => [l.label, l.sign])).toEqual([
      ['Assigned to this card', '+'],
      ['Set aside by funded spending', '+'],
      ['Released by refunds', '−'],
      ['Refunds beyond what was reserved', '−'],
      ['Paid to the card', '−'],
    ])
  })

  it('drops a leg that never moved — a month lists what happened', () => {
    const legs = reserveLegs({
      assigned: 0,
      reserved: 0,
      released: 0,
      residual: 0,
      payments: 150,
      opening: 0,
    })
    expect(legs).toHaveLength(1)
    expect(legs[0]).toEqual({ label: 'Paid to the card', value: 150, sign: '−' })
  })

  it('returns nothing at all for a month where nothing moved', () => {
    expect(
      reserveLegs({ assigned: 0, reserved: 0, released: 0, residual: 0, payments: 0, opening: 0 })
    ).toEqual([])
  })

  it('is the one table both the lifetime list and a single month read', () => {
    // The drawer shows lifetime legs above and a month's legs in an expanded
    // row. Two copies of this sign table is how a refund comes to add to the
    // reserve in one place and subtract from it in the other.
    const lifetime = reserveLegs({
      assigned: 40,
      reserved: 0,
      released: 20,
      residual: 0,
      payments: 0,
      opening: 0,
    })
    const oneMonth = reserveLegs({
      assigned: 5,
      reserved: 0,
      released: 3,
      residual: 0,
      payments: 0,
      opening: 0,
    })
    expect(lifetime.map((l) => l.sign)).toEqual(oneMonth.map((l) => l.sign))
    expect(lifetime.map((l) => l.label)).toEqual(oneMonth.map((l) => l.label))
  })
})

describe('the opening leg', () => {
  it('leads the list on an anchored budget', () => {
    const legs = reserveLegs({
      opening: 150,
      assigned: 250,
      reserved: 100,
      released: 0,
      residual: 0,
      payments: 150,
    })
    expect(legs[0]).toEqual({ label: 'Where YNAB left it at import', value: 150, sign: '+' })
  })

  it('is omitted everywhere else, like any zero leg', () => {
    const legs = reserveLegs({
      opening: 0,
      assigned: 250,
      reserved: 0,
      released: 0,
      residual: 0,
      payments: 0,
    })
    expect(legs.map((l) => l.label)).toEqual(['Assigned to this card'])
  })
})

describe('dueHeaderNote', () => {
  // The real phrasing, not a stand-in: `dueInPhrase` says "tomorrow" at one
  // day, and a helper that invented "in 1 days" would pin the wrong words.
  const at = (days: number) => ({ date: '2026-09-17', days, phrase: dueInPhrase(days) })

  it('says nothing when no bill is close', () => {
    expect(dueHeaderNote([])).toBeNull()
  })

  it('names the card when exactly one is', () => {
    // "Which card" is the question a strip with several raises, and a header
    // with no answer sends the reader to open the section to find out.
    expect(dueHeaderNote([{ name: 'Sapphire Visa', notice: at(4) }])).toBe(
      'Sapphire Visa due in 4 days'
    )
  })

  it('counts them and leads with the soonest when several are', () => {
    expect(
      dueHeaderNote([
        { name: 'Sapphire Visa', notice: at(4) },
        { name: 'Thistledown Card', notice: at(2) },
        { name: 'Harborstone Card', notice: at(6) },
      ])
    ).toBe('3 bills due, soonest in 2 days')
  })

  it('takes the soonest whatever order they arrive in', () => {
    expect(
      dueHeaderNote([
        { name: 'A', notice: at(1) },
        { name: 'B', notice: at(5) },
      ])
    ).toBe('2 bills due, soonest tomorrow')
  })
})
