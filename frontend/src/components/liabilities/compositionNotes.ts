import type { Liability } from '../../api/liabilities'

/**
 * What the payment composition lets the page finally say.
 *
 * Two findings, both of which were unsayable before a composition existed.
 *
 * The first is that the ledger and the stated payment can disagree. Every
 * payoff figure runs on principal and interest, so if the whole mortgage bill
 * is transferred into the loan account, the balance falls by the escrow as
 * well as the principal and every projection built on it runs early. The app
 * could see the discrepancy and had no vocabulary to describe it.
 *
 * The second is PMI outliving its reason. Mortgage insurance exists because
 * the loan started above eighty percent of the home's value; once equity
 * passes twenty percent a borrower may ask for it to be dropped, and nobody
 * writes to tell you the day you qualify. The app knows the balance and the
 * linked asset's value, so it can.
 *
 * Pure. Nothing here decides a number — the figures are all served — it
 * decides what to say about them, which is the part worth testing by name.
 */

export type CompositionTone = 'ok' | 'warn' | 'info'

export interface CompositionNote {
  tone: CompositionTone
  text: string
}

/**
 * Whether the transfers seen match the payment on file, said usefully.
 *
 * "Usefully" is the whole point: a bare mismatch warning is nagging. Each of
 * these says which reading the app is looking at, what that does to the
 * numbers, and what to change.
 */
export function ledgerAgreementNote(
  liability: Pick<Liability, 'composition_check' | 'composition_gap' | 'payment_components'>,
  formatMoney: (n: number) => string
): CompositionNote | null {
  const gap = liability.composition_gap
  switch (liability.composition_check) {
    case 'matches_pi':
      return {
        tone: 'ok',
        text: 'Your transfers match the principal and interest on file, so this balance means what the payoff figures assume it does.',
      }
    case 'matches_full':
      return {
        tone: 'warn',
        text:
          `Your transfers match the whole bill, so about ${gap === null ? 'the escrow' : formatMoney(gap)} a month of ` +
          'escrow is landing on the loan. That makes the balance fall faster than the debt actually does, and every ' +
          'projection here is optimistic by the same amount. Send only the principal and interest to this account, ' +
          'and put the escrow wherever the tax and insurance are budgeted.',
      }
    case 'undeclared_gap':
      return {
        tone: 'warn',
        text:
          `Your transfers run about ${gap === null ? 'more' : formatMoney(gap)} a month above the principal and interest on file. ` +
          (liability.payment_components.length > 0
            ? 'That is more than the parts listed below add up to — check the split against a statement.'
            : 'If that is escrowed tax or insurance, add it below so the bill is on record, and send only the principal and interest to this account.'),
      }
    default:
      return null
  }
}

/** Lenders must drop borrower-requested PMI at 80% loan-to-value. */
export const PMI_EQUITY_THRESHOLD = 0.2

/**
 * Whether the mortgage insurance on this bill has outlived its reason.
 *
 * Only when a PMI component is actually declared: without one there is
 * nothing to cancel, and telling somebody to ring their servicer about a
 * charge they do not pay is worse than silence.
 */
export function pmiNote(
  liability: Pick<Liability, 'payment_components'>,
  assetValue: number | null,
  equity: number | null,
  formatMoney: (n: number) => string
): CompositionNote | null {
  const pmi = liability.payment_components.find((c) => c.kind === 'pmi')
  if (!pmi) return null
  if (assetValue === null || equity === null || assetValue <= 0) {
    return {
      tone: 'info',
      text: `You pay ${formatMoney(pmi.amount)} a month in mortgage insurance. Link the home and give it a value, and this can tell you when you have enough equity to ask for it to be dropped.`,
    }
  }
  const share = equity / assetValue
  if (share >= PMI_EQUITY_THRESHOLD) {
    return {
      tone: 'warn',
      text: `You are at ${Math.round(share * 100)}% equity and still paying ${formatMoney(pmi.amount)} a month in mortgage insurance. Past 20% you can usually ask your servicer to drop it — that is ${formatMoney(pmi.amount * 12)} a year.`,
    }
  }
  const needed = assetValue * PMI_EQUITY_THRESHOLD - equity
  return {
    tone: 'info',
    text: `Mortgage insurance comes off around 20% equity. You are at ${Math.round(share * 100)}%, about ${formatMoney(needed)} of balance away.`,
  }
}
