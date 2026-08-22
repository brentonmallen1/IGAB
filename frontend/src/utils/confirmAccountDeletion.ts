// Deleting an account that tracks a debt asks a different question from
// deleting a chequing account, and the difference is not cosmetic: the debt
// still exists afterwards. Both delete call sites route through here so the
// wording — and the rule for when the question is even worth asking — has one
// home.

import type { Liability } from '../api/liabilities'
import { chooseAsync, confirmAsync } from '../stores/confirmStore'
import type { Account } from '../types'

export type LiabilityDisposition = 'keep' | 'delete'

export interface AccountDeletionChoice {
  proceed: boolean
  /** Sent to the API; ignored server-side when there is no companion. */
  liability: LiabilityDisposition
}

const CANCELLED: AccountDeletionChoice = { proceed: false, liability: 'keep' }

/**
 * Ask what should happen, and only ask the harder question when there is
 * something to lose.
 *
 * Every liability-classified account now carries a companion Liability, so
 * asking whenever one exists would put a three-way dialog in front of every
 * credit-card deletion — including the ones whose companion is an empty row
 * nobody filled in. The terms are the test: an untouched companion goes
 * quietly with its account, exactly as it arrived.
 */
export async function confirmAccountDeletion(
  account: Account,
  liabilities: Liability[]
): Promise<AccountDeletionChoice> {
  const companion = liabilities.find((l) => l.linked_account_id === account.id)

  if (!companion?.terms_complete) {
    const ok = await confirmAsync({
      title: `Delete "${account.name}"?`,
      message: 'This will also delete all its transactions. This cannot be undone.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    return ok ? { proceed: true, liability: 'keep' } : CANCELLED
  }

  const picked = await chooseAsync({
    title: `Delete account "${account.name}"?`,
    message:
      'This account has loan details — APR, minimum payment, and payoff history.\n' +
      'Its transactions will be deleted either way.',
    options: [
      {
        id: 'keep',
        label: 'Keep the debt',
        description:
          'The loan stays as a liability you track manually, keeping its balance and terms.',
      },
      {
        id: 'delete',
        label: 'Delete both',
        description: 'Removes the account and its loan details.',
        destructive: true,
      },
    ],
  })

  if (picked === null) return CANCELLED
  return { proceed: true, liability: picked === 'delete' ? 'delete' : 'keep' }
}
