/**
 * The pure half of the emergency fund picker: seeding its drafts from what is
 * served, and turning them into the one PUT a Save sends.
 */
import type { EmergencyFundChoice, FundAccountCandidate } from '../../api/emergencyFund'
import type { MembershipCategory } from '../../api/tags'
import type { FundExternal } from '../../types'
import { fromCents, parseAmountInput, toCents } from '../../utils/money'
import { membershipDiff, type MembershipDraft } from '../tags/membershipList'

export interface ExternalDraft {
  declared: boolean
  /** As typed. */
  amount: string
  note: string
}

export function externalDraft(external: FundExternal): ExternalDraft {
  return {
    declared: external.declared,
    amount: external.amount === null ? '' : String(external.amount),
    note: external.note ?? '',
  }
}

export function memberAccounts(candidates: readonly FundAccountCandidate[]): Set<string> {
  return new Set(candidates.filter((c) => c.member).map((c) => c.id))
}

/** Checked accounts that do not count as savings yet — the save turns it on. */
export function turnsOnSavings(
  candidates: readonly FundAccountCandidate[],
  checked: ReadonlySet<string>
): Set<string> {
  return new Set(
    candidates.filter((c) => checked.has(c.id) && !c.counts_as_savings).map((c) => c.id)
  )
}

export const AMOUNT_ERROR = 'Enter an amount like 1,000 — or leave it blank if you’d rather not say'

/** The kept-elsewhere part of the save. Typed by a person, so
 *  `parseAmountInput`: blank is "I have this covered" (null); anything
 *  unreadable is an error — never booked as zero. */
export function parseExternal(
  draft: ExternalDraft
): { value: EmergencyFundChoice['external'] } | { error: string } {
  if (!draft.declared) return { value: { declared: false, amount: null, note: null } }
  const note = draft.note.trim() || null
  if (draft.amount.trim() === '') return { value: { declared: true, amount: null, note } }
  const n = parseAmountInput(draft.amount)
  if (Number.isNaN(n)) return { error: AMOUNT_ERROR }
  return { value: { declared: true, amount: fromCents(toCents(n)).toFixed(2), note } }
}

export function buildChoice(input: {
  rows: readonly MembershipCategory[]
  envelopes: MembershipDraft
  accounts: ReadonlySet<string>
  external: ExternalDraft
}): { choice: EmergencyFundChoice } | { error: string } {
  const external = parseExternal(input.external)
  if ('error' in external) return external
  const envelopes = membershipDiff(input.rows, input.envelopes)
  return {
    choice: {
      add_categories: envelopes.add,
      remove_categories: envelopes.remove,
      savings_modes: envelopes.savings_modes,
      account_ids: [...input.accounts].sort(),
      external: external.value,
    },
  }
}
