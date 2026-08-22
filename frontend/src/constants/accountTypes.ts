// Frontend mirror of the built-in account types seeded for every budget.
// Canonical wording lives in the backend seed (backend/src/igab/domain/
// account_types.py) — keep the two in step. This constant exists for the one
// context where the registry can't be fetched: the YNAB import mapping step,
// which runs BEFORE the budget (and therefore its registry) exists.

export interface AccountTypeOption {
  key: string
  label: string
  classification: 'asset' | 'liability'
  default_on_budget: boolean
  description: string
}

export const BUILTIN_ACCOUNT_TYPES: AccountTypeOption[] = [
  {
    key: 'checking',
    label: 'Checking',
    classification: 'asset',
    default_on_budget: true,
    description:
      'Everyday spending account. On budget: its balance funds your envelopes, and ' +
      'spending from it needs a category. Moving money between two on-budget ' +
      'accounts is neither income nor spending.',
  },
  {
    key: 'savings',
    label: 'Savings',
    classification: 'asset',
    default_on_budget: true,
    description:
      'Money set aside but still yours to plan with. On budget so it can back ' +
      'envelopes like an emergency fund. Because it is on budget, moving money here ' +
      'is not counted as saving — the money never left your budget. Tag a category ' +
      'as Savings if you want it counted.',
  },
  {
    key: 'cash',
    label: 'Cash',
    classification: 'asset',
    default_on_budget: true,
    description: 'Physical cash. Works exactly like checking, just tracked by hand.',
  },
  {
    key: 'credit_card',
    label: 'Credit Card',
    classification: 'liability',
    default_on_budget: true,
    description:
      'Card debt tracked transaction by transaction. On budget: card spending uses ' +
      'envelope money, and payments are transfers.',
  },
  {
    key: 'loan',
    label: 'Loan',
    classification: 'liability',
    default_on_budget: false,
    description:
      'A mortgage, auto, student, or other loan. Usually off budget — link a ' +
      'Liability record to it for payoff projections. Money you send here counts as ' +
      'paying down debt, not spending, so it stays out of your spending reports.',
  },
  {
    key: 'investment',
    label: 'Investment',
    classification: 'asset',
    default_on_budget: false,
    description:
      'Brokerage, retirement (401k, IRA), HSA, or similar. Off budget: it grows ' +
      'your net worth but isn\'t spendable envelope money. Money you move here ' +
      'counts as saving rather than spending. Growth inside the account — ' +
      'dividends, market movement — is not counted as saving, because you didn\'t ' +
      'put it there.',
  },
  {
    key: 'other_asset',
    label: 'Other Asset',
    classification: 'asset',
    default_on_budget: false,
    description:
      'Anything else you own that counts toward net worth — property value, crypto, ' +
      'a manually tracked balance. Off budget, so money moved here counts as saving ' +
      'rather than spending.',
  },
  {
    key: 'other_liability',
    label: 'Other Liability',
    classification: 'liability',
    default_on_budget: false,
    description:
      'Anything else you owe that counts against net worth but isn\'t budgeted ' +
      'transaction by transaction. Money you send here counts as paying down debt ' +
      'rather than spending.',
  },
]

const BUILTIN_LABELS = new Map(BUILTIN_ACCOUNT_TYPES.map((t) => [t.key, t.label]))

/** Display label for a type key: the registry row's label when available,
 * else the built-in label, else the key title-cased (custom types are only
 * unknown while the registry query is still loading). */
export function accountTypeLabel(
  key: string,
  registry?: { key: string; label: string }[]
): string {
  const fromRegistry = registry?.find((t) => t.key === key)?.label
  if (fromRegistry) return fromRegistry
  const builtin = BUILTIN_LABELS.get(key)
  if (builtin) return builtin
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
