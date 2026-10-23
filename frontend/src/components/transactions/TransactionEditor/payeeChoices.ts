import type { Account, Payee } from '../../../types'
import { choosablePayees } from '../../../utils/payees'
import { transferPayeeLabel } from '../transferConversion'

/**
 * What the editor's payee box offers for what has been typed: payees, and
 * separately the accounts a transfer could go to.
 *
 * Apart because they are different answers. A transfer payee picked by name
 * used to be the one edit the save never read — the body takes a transfer's
 * account from the account control — so "Transfer : Harborstone Checking"
 * picked in the box closed the dialog and changed nothing. Destinations are
 * accounts, and picking one drives the account control.
 */
export function payeeChoices({
  query,
  payees,
  accounts,
  targets,
  shownTransferLabel,
}: {
  query: string
  payees: Payee[]
  accounts: Account[]
  /** The accounts this row may transfer to (`transferTargets`). */
  targets: Account[]
  /** What the box reads while it shows a transfer's destination, or null. */
  shownTransferLabel: string | null
}): { payees: Payee[]; transfers: Account[] } {
  const q = query.toLowerCase()
  // The box already showing the destination is a reading, not a search.
  const tq = shownTransferLabel !== null && query === shownTransferLabel ? '' : q
  return {
    payees: choosablePayees(payees)
      .filter((p) => !q || p.name.toLowerCase().includes(q))
      .slice(0, 8),
    // Matched on the register's own wording too: someone who types
    // "Transfer" is looking for exactly these.
    transfers: targets
      .filter(
        (a) =>
          !tq ||
          a.name.toLowerCase().includes(tq) ||
          transferPayeeLabel(a.id, accounts, payees).toLowerCase().includes(tq)
      )
      .slice(0, 6),
  }
}
