import type { Account } from '../../../types'
import { isCardAccount, isLiabilityAccount } from '../../../utils/accountKinds'

/**
 * Whether this register's toolbar offers a payment, and what to call it.
 *
 * The action belongs beside Add Transaction because that is where "do a thing
 * to this account" lives — it used to sit at the end of the APR stats strip,
 * styled like "Edit terms", and read as metadata instead of a button.
 *
 * Kind comes from `accountKinds.ts`, never re-derived: a liability takes a
 * payment whether it is a card (on-budget) or a loan (off-budget), and the
 * wording follows — a card payment is made, a loan payment already happened
 * elsewhere and is recorded.
 */
export function registerPayAction(
  accounts: Pick<Account, 'id' | 'on_budget' | 'classification'>[],
  accountId: string | null
): { label: string } | null {
  if (accountId === null) return null // the all-accounts register pays nobody
  const account = accounts.find((a) => a.id === accountId)
  if (!account || !isLiabilityAccount(account)) return null
  return { label: isCardAccount(account) ? 'Make a payment' : 'Record a payment' }
}
