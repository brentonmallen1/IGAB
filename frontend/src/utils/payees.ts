import type { Payee } from '../types'

/**
 * Which payees a person may pick as a payee.
 *
 * A transfer payee ("Transfer : Harborstone Checking") is a destination, not
 * a payee: the server creates one per account and a leg's payee names the
 * account at the other end. Picking one by name would name a transfer the
 * row is not — or, in the transaction editor, do nothing at all, because the
 * editor sends a transfer's account from its own control and never read the
 * payee box (the "Payee Not Sent" report). Destinations are offered as
 * accounts, under their own heading (`transferConversion.transferOptions`).
 *
 * The rule was written out nine times — the register cell, Quick Add (twice),
 * the report filter, the Payees page (three times) and the merge dialog
 * (twice) — and missing from two: the transaction editor and the command
 * palette. The extra terms some of those sites add (recency, a merge group)
 * stay with them; this is only the part they all meant.
 */

/** A payee the server made to name an account, not a payee anyone chose. */
export function isTransferPayee(p: Pick<Payee, 'transfer_account_id'>): boolean {
  return !!p.transfer_account_id
}

/** The payees a picker may offer: every one but the transfer payees. */
export function choosablePayees<P extends Pick<Payee, 'transfer_account_id'>>(payees: P[]): P[] {
  return payees.filter((p) => !isTransferPayee(p))
}
