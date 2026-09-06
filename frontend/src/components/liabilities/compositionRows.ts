import type { PaymentComponentInput, PaymentComponentKind } from '../../api/liabilities'
import { parseAmountInput } from '../../utils/money'

/**
 * The rules behind the escrow editor, without the editor.
 *
 * Split from the component per this repo's convention: logic that can only be
 * exercised by mounting a form is logic that stops being tested. What is here
 * is the part with opinions — which rows count, which amounts are refused
 * rather than booked as zero, and what the declared bill comes to.
 */

export const COMPONENT_KINDS: { value: PaymentComponentKind; label: string }[] = [
  { value: 'tax', label: 'Property tax' },
  { value: 'insurance', label: 'Insurance' },
  { value: 'pmi', label: 'Mortgage insurance (PMI)' },
  { value: 'hoa', label: 'HOA dues' },
  { value: 'other', label: 'Other' },
]

export const MAX_COMPONENTS = 8

export function blankComponent(): PaymentComponentInput {
  return { kind: 'tax', label: '', amount: '' }
}

/** Rows worth sending: a blank one is someone who changed their mind. */
export function usableComponents(rows: PaymentComponentInput[]): PaymentComponentInput[] {
  return rows.filter((row) => row.amount.trim() !== '')
}

/** Which rows carry an amount that does not parse — never booked as zero. */
export function invalidComponentIndexes(rows: PaymentComponentInput[]): number[] {
  return rows.flatMap((row, index) => {
    if (row.amount.trim() === '') return []
    const parsed = parseAmountInput(row.amount)
    return Number.isNaN(parsed) || parsed < 0 ? [index] : []
  })
}

/** The declared bill: P&I plus the parts. Null when either half is unusable,
 *  because a total missing its largest term reads as a complete one. */
export function declaredTotal(
  principalAndInterest: string,
  rows: PaymentComponentInput[]
): number | null {
  const pi = parseAmountInput(principalAndInterest)
  if (Number.isNaN(pi) || principalAndInterest.trim() === '') return null
  if (invalidComponentIndexes(rows).length > 0) return null
  return usableComponents(rows).reduce((sum, row) => sum + parseAmountInput(row.amount), pi)
}
