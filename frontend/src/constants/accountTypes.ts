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
      'Everyday spending account. On budget: its balance funds your envelopes, ' +
      'and spending from it needs a category.',
  },
  {
    key: 'savings',
    label: 'Savings',
    classification: 'asset',
    default_on_budget: true,
    description:
      'Money set aside but still yours to plan with. On budget so it can back ' +
      'envelopes like an emergency fund.',
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
      'Card debt tracked transaction by transaction. On budget: card spending ' +
      'uses envelope money, and payments are transfers.',
  },
  {
    key: 'loan',
    label: 'Loan',
    classification: 'liability',
    default_on_budget: false,
    description:
      'A mortgage, auto, student, or other loan. Usually off budget — link a ' +
      'Liability record to it for payoff projections.',
  },
  {
    key: 'investment',
    label: 'Investment',
    classification: 'asset',
    default_on_budget: false,
    description:
      "Brokerage, retirement (401k, IRA), HSA, or similar. Off budget: it grows " +
      "your net worth but isn't spendable envelope money.",
  },
  {
    key: 'other_asset',
    label: 'Other Asset',
    classification: 'asset',
    default_on_budget: false,
    description:
      'Anything else you own that counts toward net worth — property value, ' +
      'crypto, a manually tracked balance.',
  },
  {
    key: 'other_liability',
    label: 'Other Liability',
    classification: 'liability',
    default_on_budget: false,
    description:
      "Anything else you owe that counts against net worth but isn't budgeted " +
      'transaction by transaction.',
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
