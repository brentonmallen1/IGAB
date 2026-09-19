import type { Account, Transaction } from '../../types'
import type { ComboboxOption } from '../common/Combobox/Combobox'

/**
 * Turning an ordinary row into a transfer — the parts that are decisions
 * rather than markup.
 *
 * Three surfaces ask for this conversion now: the editor's "Transfer to
 * account" toggle, the register's selection bar, and the register's inline
 * payee picker. The *request* they send has to be identical — a link made
 * from the register must be indistinguishable from one made in the editor —
 * so the payload and the "may I send this yet?" rule live here once, and the
 * three surfaces differ only in how they ask the questions.
 *
 * Pure: options in, options out. The wiring (queries, mutations, dialogs)
 * stays with each caller.
 */

/** The partner answer meaning "none of these — write the far leg for me". */
export const CREATE_NEW_PARTNER = '__create__'

/** Prefix marking a payee-picker option that is an account, not a payee. */
const TRANSFER_OPTION_PREFIX = 'transfer:'

/** The PATCH fields that make a row a transfer to `accountId`.
 *
 *  `transfer_account_id` alone is enough when the server has no ambiguity to
 *  resolve; `partnerChoice` answers it when it does. Sending money fields
 *  beside these is refused server-side (TransactionService.update) — a link
 *  edit changes the link, nothing else. */
export function transferLinkFields(
  accountId: string,
  partnerChoice: string | null
): {
  transfer_account_id: string
  transfer_create_partner?: true
  transfer_partner_transaction_id?: string
} {
  return {
    transfer_account_id: accountId,
    ...(partnerChoice === CREATE_NEW_PARTNER
      ? { transfer_create_partner: true as const }
      : partnerChoice
        ? { transfer_partner_transaction_id: partnerChoice }
        : {}),
  }
}

/** Is the conversion still waiting on a person?
 *
 *  Which row over there is this transfer's other half is only answerable by
 *  a human, and the server refuses a submit that does not say — so every
 *  surface holds its save rather than sending a request that can only fail. */
export function awaitingPartnerChoice(
  candidates: Pick<Transaction, 'id'>[],
  partnerChoice: string | null
): boolean {
  return candidates.length > 0 && !partnerChoice
}

/** May this row be turned into a transfer at all?
 *
 *  Three surfaces offer the conversion and all three must offer it on the
 *  same rows — an action that appears in the register and is refused on save
 *  is worse than one that never appeared. The server's own refusals are in
 *  `TransactionService.update`: a split (or one of its lines) cannot be a
 *  leg, and a row that is already linked is retargeted rather than
 *  converted. Reconciled is this side's own restraint, matching the editor's
 *  toggle: the link is bookkeeping the server would take, but an unlocked
 *  row is what the register lets you edit at all.
 *
 *  An already-linked leg is NOT convertible here: changing where a linked
 *  transfer points moves its partner, which is the editor's job. */
export function mayBecomeTransfer(
  txn: Pick<Transaction, 'transfer_id' | 'is_split' | 'parent_transaction_id' | 'cleared'>
): boolean {
  return (
    !txn.transfer_id && !txn.is_split && !txn.parent_transaction_id && txn.cleared !== 'reconciled'
  )
}

/** The accounts a row in `ownAccountId` may transfer to: every open account
 *  but its own. A closed account is refused server-side
 *  (domain/account_move), and offering it would be offering a refusal. */
export function transferTargets(accounts: Account[], ownAccountId: string): Account[] {
  return accounts.filter((a) => a.id !== ownAccountId && !a.is_closed)
}

/** Transfer destinations as payee-picker options, under their own heading.
 *
 *  The register's payee picker hides transfer payees on purpose — picking
 *  one would *name* a transfer the row is not (rowOptions.payeeOptions). But
 *  a payee genuinely called "Online Transfer" is offered, so the list gave
 *  no way to tell a name from a destination. These options are destinations,
 *  say so in their own group, and carry an id no payee can collide with. */
export function transferOptions(accounts: Account[], ownAccountId: string): ComboboxOption[] {
  return transferTargets(accounts, ownAccountId).map((a) => ({
    id: TRANSFER_OPTION_PREFIX + a.id,
    label: a.name,
    group: 'Transfer to account',
  }))
}

/** The account id behind a `transferOptions` id, or null for a real payee. */
export function transferOptionAccountId(optionId: string | null): string | null {
  if (!optionId || !optionId.startsWith(TRANSFER_OPTION_PREFIX)) return null
  return optionId.slice(TRANSFER_OPTION_PREFIX.length) || null
}
