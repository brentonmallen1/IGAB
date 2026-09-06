/**
 * The two things a payment composition lets the page say.
 *
 * The brief behind these: "if the system doesn't at least tell the user what
 * they should or shouldn't include in their stated mortgage payment, it might
 * not be helpful or obvious." So a bare mismatch warning is not the feature —
 * each note has to name which reading the app is looking at, what it does to
 * the numbers, and what to change.
 */
import { describe, expect, it } from 'vitest'
import type { Liability, PaymentComponent } from '../../api/liabilities'
import { ledgerAgreementNote, pmiNote } from './compositionNotes'

const money = (n: number) => `$${n.toLocaleString('en-US', { minimumFractionDigits: 2 })}`

const PMI: PaymentComponent = { kind: 'pmi', label: 'PMI', amount: 42.8 }
const TAX: PaymentComponent = { kind: 'tax', label: 'Property tax', amount: 410 }

function liability(over: Partial<Liability> = {}) {
  return {
    composition_check: 'unknown',
    composition_gap: null,
    payment_components: [],
    ...over,
  } as Pick<Liability, 'composition_check' | 'composition_gap' | 'payment_components'>
}

describe('does the ledger agree with the stated payment', () => {
  it('says nothing without enough history to judge', () => {
    expect(ledgerAgreementNote(liability(), money)).toBeNull()
  })

  it('confirms the healthy shape rather than staying silent about it', () => {
    // Silence reads as "not checked". This is the one case where the numbers
    // can be trusted, and saying so is what makes the warnings meaningful.
    const note = ledgerAgreementNote(liability({ composition_check: 'matches_pi' }), money)
    expect(note?.tone).toBe('ok')
    expect(note?.text).toMatch(/means what the payoff figures assume/)
  })

  it('explains what paying the whole bill into the loan does to the numbers', () => {
    const note = ledgerAgreementNote(
      liability({
        composition_check: 'matches_full',
        composition_gap: 547.8,
        payment_components: [TAX],
      }),
      money
    )
    expect(note?.tone).toBe('warn')
    expect(note?.text).toContain('$547.80')
    // Names the consequence and the fix, not just the discrepancy.
    expect(note?.text).toMatch(/balance fall faster/)
    expect(note?.text).toMatch(/Send only the principal and interest/)
  })

  it('tells a user with no composition on file what the field is for', () => {
    const note = ledgerAgreementNote(
      liability({ composition_check: 'undeclared_gap', composition_gap: 547.8 }),
      money
    )
    expect(note?.tone).toBe('warn')
    expect(note?.text).toMatch(/add it below/)
  })

  it('points at the split itself when one is declared and still does not add up', () => {
    const note = ledgerAgreementNote(
      liability({
        composition_check: 'undeclared_gap',
        composition_gap: 547.8,
        payment_components: [TAX],
      }),
      money
    )
    expect(note?.text).toMatch(/check the split against a statement/)
  })
})

describe('mortgage insurance outliving its reason', () => {
  it('says nothing when none is declared', () => {
    // Telling somebody to ring their servicer about a charge they do not pay
    // is worse than silence.
    expect(pmiNote(liability({ payment_components: [TAX] }), 400000, 200000, money)).toBeNull()
  })

  it('flags it once equity passes twenty percent, with the yearly cost', () => {
    const note = pmiNote(liability({ payment_components: [PMI] }), 400000, 100000, money)
    expect(note?.tone).toBe('warn')
    expect(note?.text).toContain('25% equity')
    expect(note?.text).toMatch(/ask your servicer to drop it/)
    expect(note?.text).toContain('$513.60')
  })

  it('says how far there is to go while it is still justified', () => {
    const note = pmiNote(liability({ payment_components: [PMI] }), 400000, 40000, money)
    expect(note?.tone).toBe('info')
    expect(note?.text).toContain('10%')
    expect(note?.text).toContain('$40,000.00')
  })

  it('treats exactly twenty percent as reached', () => {
    const note = pmiNote(liability({ payment_components: [PMI] }), 400000, 80000, money)
    expect(note?.tone).toBe('warn')
  })

  it('asks for a home value rather than guessing at one', () => {
    const note = pmiNote(liability({ payment_components: [PMI] }), null, null, money)
    expect(note?.tone).toBe('info')
    expect(note?.text).toMatch(/Link the home and give it a value/)
  })
})
