/**
 * What kind of account this is, for the credit model — the client half of
 * the rule whose one server home is `txn_filters.py`:
 *
 * - `CARD_ACCOUNT`: an on-budget, liability-classified account. By
 *   classification, never the type string — a custom on-budget liability
 *   type (a HELOC, a line of credit) behaves identically, and matching
 *   `account_type === 'credit_card'` would silently exempt it.
 * - `CASH_ACCOUNT`: on-budget and NOT a liability — the budget's cash, the
 *   balance term of Ready to Assign, and the only accounts a card payment
 *   may be supplied from (`CARD_PAYMENT_FROM_CASH`).
 *
 * Irreducible duplication, one implementation per side (the
 * `rowCategoryRule.ts` pattern): the server refuses nothing here — it
 * normalises — so a picker offering the wrong account would file money
 * somewhere the credit model cannot see. Every client ask of "is this a
 * card / is this cash" reads these and nothing else.
 */

interface AccountKindFields {
  on_budget: boolean
  classification: 'asset' | 'liability' | null
}

export function isCardAccount(account: AccountKindFields): boolean {
  return account.on_budget && account.classification === 'liability'
}

export function isCashAccount(account: AccountKindFields): boolean {
  return account.on_budget && account.classification !== 'liability'
}
