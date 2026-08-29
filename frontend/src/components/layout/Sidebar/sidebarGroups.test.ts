import { describe, expect, it } from 'vitest'
import type { Account } from '../../../types'
import {
  accountKind,
  accountTarget,
  accountsTotal,
  balanceTone,
  buildLiabilityRows,
  groupLabel,
  isRowActive,
  onBudgetTotals,
  liabilityHeaderTotal,
  orderedOnBudgetKeys,
  parseSidebarLocation,
  partitionAccounts,
  type LiabilitySummary,
} from './sidebarGroups'

let seq = 0
function acct(over: Partial<Account>): Account {
  seq += 1
  return {
    id: over.id ?? `acct-${seq}`,
    budget_id: 'b1',
    name: 'Account',
    account_type: 'checking',
    on_budget: true,
    classification: 'asset',
    is_closed: false,
    sort_order: 0,
    note: null,
    balance: 0,
    cleared_balance: 0,
    uncleared_balance: 0,
    uncategorized_count: 0,
    ...over,
  } as Account
}

function liab(over: Partial<LiabilitySummary>): LiabilitySummary {
  seq += 1
  return {
    id: over.id ?? `liab-${seq}`,
    name: 'Liability',
    linked_account_id: null,
    current_balance: 0,
    ...over,
  }
}

describe('partitionAccounts', () => {
  it('sends every account to exactly one section', () => {
    const accounts = [
      acct({ account_type: 'checking' }),
      acct({ account_type: 'pension_fund', on_budget: true }),
      acct({ on_budget: false, classification: 'asset', account_type: 'investment' }),
      acct({ on_budget: false, classification: 'liability', account_type: 'loan' }),
    ]
    const p = partitionAccounts(accounts)
    const placed =
      [...p.onBudgetByType.values()].flat().length +
      p.offBudgetAssets.length +
      p.offBudgetLiabilityAccounts.length
    expect(placed).toBe(accounts.length)
    expect(p.onBudgetByType.get('pension_fund')).toHaveLength(1)
    expect(p.offBudgetAssets).toHaveLength(1)
    expect(p.offBudgetLiabilityAccounts).toHaveLength(1)
  })

  it('lands a legacy NULL classification in assets rather than nowhere', () => {
    const stray = acct({
      on_budget: false,
      classification: null,
      account_type: 'investment',
    })
    const p = partitionAccounts([stray])
    expect(p.offBudgetAssets).toEqual([stray])
    expect(p.offBudgetLiabilityAccounts).toEqual([])
  })
})

describe('orderedOnBudgetKeys', () => {
  it('orders built-ins canonically and custom keys after, alphabetically', () => {
    const p = partitionAccounts([
      acct({ account_type: 'zebra_fund' }),
      acct({ account_type: 'loan', on_budget: true, classification: 'liability' }),
      acct({ account_type: 'checking' }),
      acct({ account_type: 'aardvark' }),
      acct({ account_type: 'cash' }),
    ])
    expect(orderedOnBudgetKeys(p.onBudgetByType)).toEqual([
      'checking',
      'cash',
      'loan',
      'aardvark',
      'zebra_fund',
    ])
  })
})

describe('buildLiabilityRows', () => {
  it('shows the tracker balance for a managed account with an empty ledger', () => {
    const loanAccount = acct({
      id: 'loan-acct',
      on_budget: false,
      classification: 'liability',
      account_type: 'loan',
      balance: 0,
    })
    const tracker = liab({ linked_account_id: 'loan-acct', current_balance: 250_000 })
    const rows = buildLiabilityRows([loanAccount], [tracker])
    expect(rows).toHaveLength(1)
    expect(rows[0].balance).toBe(-250_000)
    expect(rows[0].target).toEqual({ kind: 'liability', liabilityId: tracker.id })
    expect(rows[0].registerAccountId).toBe('loan-acct')
    expect(rows[0].icon).toBe('managed')
  })

  it('renders a managed liability exactly once when its account is on budget', () => {
    // The linked account lives in Budget Accounts, so it is NOT in the
    // off-budget liability set — the liability itself must still show.
    const tracker = liab({
      name: 'Mortgage',
      linked_account_id: 'on-budget-acct',
      current_balance: 180_000,
    })
    const rows = buildLiabilityRows([], [tracker])
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('Mortgage')
    expect(rows[0].balance).toBe(-180_000)
    expect(rows[0].icon).toBe('managed')
    expect(rows[0].registerAccountId).toBeNull()
  })

  it('handles the mixed case with no double counting', () => {
    const linkedAccount = acct({
      id: 'car-acct',
      on_budget: false,
      classification: 'liability',
      balance: -9480,
    })
    const bareAccount = acct({
      id: 'cc-acct',
      on_budget: false,
      classification: 'liability',
      balance: -420,
    })
    const carTracker = liab({ linked_account_id: 'car-acct', current_balance: 9480 })
    const orphanTracker = liab({ linked_account_id: 'missing-acct', current_balance: 1000 })
    const unmanaged = liab({ current_balance: 855 })

    const rows = buildLiabilityRows([linkedAccount, bareAccount], [
      carTracker,
      orphanTracker,
      unmanaged,
    ])
    expect(rows).toHaveLength(4)
    expect(liabilityHeaderTotal(rows)).toBe(-9480 - 420 - 1000 - 855)
  })

  it('marks unmanaged liabilities as manual', () => {
    const rows = buildLiabilityRows([], [liab({ current_balance: 855 })])
    expect(rows[0].icon).toBe('manual')
    expect(rows[0].balance).toBe(-855)
  })
})

describe('accountsTotal', () => {
  it('sums off-budget asset balances', () => {
    const p = partitionAccounts([
      acct({ on_budget: false, classification: 'asset', balance: 12_000 }),
      acct({ on_budget: false, classification: 'asset', balance: 500.5 }),
    ])
    expect(accountsTotal(p.offBudgetAssets)).toBeCloseTo(12_500.5)
  })

  it('sums a negative balance as owed, not as nothing', () => {
    expect(accountsTotal([acct({ balance: 100 }), acct({ balance: -250 })])).toBe(-150)
  })

  it('is zero for an empty group rather than NaN', () => {
    expect(accountsTotal([])).toBe(0)
  })
})

describe('onBudgetTotals', () => {
  const budget = () =>
    partitionAccounts([
      acct({ account_type: 'checking', balance: 1200 }),
      acct({ account_type: 'checking', balance: 340.25 }),
      acct({ account_type: 'savings', balance: 8000 }),
      acct({ account_type: 'credit_card', classification: 'liability', balance: -450.5 }),
      acct({ on_budget: false, classification: 'asset', balance: 99_999 }),
    ]).onBudgetByType

  // The Budget Accounts header must equal the sum of the type subtotals drawn
  // beneath it, collapsed or not — the header used to be computed from a
  // separate filter over `accounts`, so any divergence between that filter and
  // the partition would have shown as a header that did not add up.
  it('nets to the sum of the per-type subtotals it renders', () => {
    const onBudgetByType = budget()
    const perType = [...onBudgetByType.values()].map(accountsTotal)

    expect(onBudgetTotals(onBudgetByType).net).toBeCloseTo(perType.reduce((a, b) => a + b, 0))
    expect(onBudgetTotals(onBudgetByType).net).toBeCloseTo(9089.75)
  })

  // The number the sidebar had no way to say: a card is on budget, but its
  // balance is not money you have, and the budget's own cash term stopped
  // counting it when cards left Ready to Assign.
  it('counts cash without the cards', () => {
    expect(onBudgetTotals(budget()).cash).toBeCloseTo(9540.25)
  })

  it('counts what the cards owe, on their own', () => {
    expect(onBudgetTotals(budget()).cards).toBeCloseTo(-450.5)
  })

  it('keeps cash and cards adding back up to the header', () => {
    const { cash, cards, net } = onBudgetTotals(budget())
    expect(cash + cards).toBeCloseTo(net)
  })

  it('reads an on-budget liability as a card whatever its type is called', () => {
    // The partition is classification, not account_type — a HELOC or a
    // store-card type nobody has heard of behaves the same way.
    const { onBudgetByType } = partitionAccounts([
      acct({ account_type: 'heloc', classification: 'liability', balance: -900 }),
      acct({ account_type: 'checking', balance: 100 }),
    ])

    expect(onBudgetTotals(onBudgetByType)).toMatchObject({ cash: 100, cards: -900, net: -800 })
  })

  it('says cash is the whole story when no card is on budget', () => {
    const { onBudgetByType } = partitionAccounts([acct({ balance: 500 })])
    const totals = onBudgetTotals(onBudgetByType)

    // The row that prints `cash` is drawn only when cards are non-zero,
    // precisely so the sidebar never shows the same number twice.
    expect(totals).toMatchObject({ cash: 500, cards: 0, net: 500 })
  })

  it('is zero with no on-budget accounts', () => {
    expect(onBudgetTotals(new Map())).toMatchObject({ cash: 0, cards: 0, net: 0 })
  })
})

describe('groupLabel', () => {
  // Each of these was a hand-written case in the sidebar's own switch. They
  // are asserted by name because that switch was a second copy of the built-in
  // wording: renaming a type in the registry left the header on the old name.
  it('pluralizes countable built-in type labels', () => {
    expect(groupLabel('credit_card')).toBe('Credit Cards')
    expect(groupLabel('mortgage')).toBe('Mortgages')
    expect(groupLabel('auto_loan')).toBe('Auto Loans')
    expect(groupLabel('student_loan')).toBe('Student Loans')
    expect(groupLabel('loan')).toBe('Loans')
    expect(groupLabel('investment')).toBe('Investments')
    expect(groupLabel('other_asset')).toBe('Other Assets')
    expect(groupLabel('other_liability')).toBe('Other Liabilities')
  })

  it('leaves labels that already name a set alone', () => {
    expect(groupLabel('checking')).toBe('Checking')
    expect(groupLabel('cash')).toBe('Cash')
    expect(groupLabel('savings')).toBe('Savings')
    expect(groupLabel('tracking')).toBe('Tracking')
  })

  it('takes the wording from the registry, so a renamed type renames its header', () => {
    expect(groupLabel('credit_card', [{ key: 'credit_card', label: 'Charge Card' }])).toBe(
      'Charge Cards'
    )
  })

  it('pluralizes a consonant + y as -ies', () => {
    expect(groupLabel('other_liability')).toBe('Other Liabilities')
    expect(groupLabel('annuity', [{ key: 'annuity', label: 'Annuity' }])).toBe('Annuities')
    // vowel + y is a plain -s: "Moneies" is not a word
    expect(groupLabel('play_money', [{ key: 'play_money', label: 'Play Money' }])).toBe(
      'Play Moneys'
    )
  })

  it('pluralizes a custom type, and does not double an s', () => {
    expect(groupLabel('crypto_wallet', [{ key: 'crypto_wallet', label: 'Crypto Wallet' }])).toBe(
      'Crypto Wallets'
    )
    expect(groupLabel('premises', [{ key: 'premises', label: 'Premises' }])).toBe('Premises')
  })
})

describe('buildLiabilityRows with a companion on every liability account', () => {
  // The rule "every liability-classified account carries a Liability row" is
  // new, and it makes a shape that used to be rare — a managed liability whose
  // linked account is ON budget — the norm for credit cards. Each of these
  // asserts against that fixture rather than trusting the older cases, which
  // were all written when a companion was something a user opted into.

  it('lists an on-budget card once, in the accounts section, not twice', () => {
    const visa = acct({
      id: 'visa',
      name: 'Sapphire Visa',
      account_type: 'credit_card',
      on_budget: true,
      classification: 'liability',
      balance: -420,
    })
    const companion = liab({ name: 'Sapphire Visa', linked_account_id: 'visa', current_balance: 420 })
    const { offBudgetLiabilityAccounts } = partitionAccounts([visa])

    const rows = buildLiabilityRows(offBudgetLiabilityAccounts, [companion], new Set(['visa']))

    expect(rows).toEqual([])
  })

  it('keeps the header total off the double count that would follow', () => {
    const visa = acct({
      id: 'visa',
      account_type: 'credit_card',
      on_budget: true,
      classification: 'liability',
      balance: -420,
    })
    const mortgage = acct({
      id: 'mortgage',
      name: 'Mortgage',
      account_type: 'loan',
      on_budget: false,
      classification: 'liability',
      balance: -286000,
    })
    const liabilities = [
      liab({ name: 'Visa', linked_account_id: 'visa', current_balance: 420 }),
      liab({ name: 'Maple St Mortgage', linked_account_id: 'mortgage', current_balance: 286000 }),
    ]
    const { offBudgetLiabilityAccounts } = partitionAccounts([visa, mortgage])

    const rows = buildLiabilityRows(offBudgetLiabilityAccounts, liabilities, new Set(['visa']))

    // The card's debt is counted in the on-budget total, so counting it here
    // too would state the household owes $420 more than it does.
    expect(liabilityHeaderTotal(rows)).toBe(-286000)
  })

  it('still renders an off-budget loan once, through its companion', () => {
    const loan = acct({
      id: 'loan',
      name: 'Car Loan',
      account_type: 'loan',
      on_budget: false,
      classification: 'liability',
      balance: -9480,
    })
    const companion = liab({ name: 'Car Loan', linked_account_id: 'loan', current_balance: 9480 })
    const { offBudgetLiabilityAccounts } = partitionAccounts([loan])

    const rows = buildLiabilityRows(offBudgetLiabilityAccounts, [companion], new Set())

    expect(rows).toHaveLength(1)
    expect(rows[0].target).toEqual({ kind: 'liability', liabilityId: companion.id })
    expect(rows[0].registerAccountId).toBe('loan')
    expect(rows[0].balance).toBe(-9480)
  })

  it('still lists a liability whose linked account is closed and off budget', () => {
    // The case the second loop exists for: nothing else renders it.
    const orphaned = liab({
      name: 'Old Store Card',
      linked_account_id: 'closed-card',
      current_balance: 250,
    })

    const rows = buildLiabilityRows([], [orphaned], new Set())

    expect(rows).toHaveLength(1)
    expect(rows[0].icon).toBe('managed')
  })

  it('still lists unmanaged liabilities', () => {
    const manual = liab({ name: 'Family Loan', current_balance: 1200 })

    const rows = buildLiabilityRows([], [manual], new Set(['some-other-account']))

    expect(rows).toHaveLength(1)
    expect(rows[0].icon).toBe('manual')
  })
})

/**
 * What a minus sign means depends on what the account is, and the sidebar
 * used to ignore that: every negative balance rendered red, so a mortgage, a
 * car loan and three credit cards showed as five alarms on an ordinary
 * Tuesday. A person learns to stop reading red that is always there.
 */
describe('balanceTone', () => {
  it('marks an asset in the red — that is overdrawn, and it is news', () => {
    expect(balanceTone(-55.68, 'asset')).toBe('negative')
  })

  it('leaves a debt showing what it owes alone', () => {
    expect(balanceTone(-1204.13, 'debt')).toBe('neutral')
  })

  it('has nothing to say about money in the bank', () => {
    expect(balanceTone(7865.9, 'asset')).toBe('neutral')
    expect(balanceTone(0, 'asset')).toBe('neutral')
  })

  it('says nothing about an overpaid card either', () => {
    // A positive balance on a debt is a credit — unusual, not a problem.
    expect(balanceTone(40, 'debt')).toBe('neutral')
  })
})

describe('accountKind', () => {
  it('reads a credit card as a debt even though it is on budget', () => {
    expect(accountKind(acct({ classification: 'liability', on_budget: true }))).toBe('debt')
  })

  it('reads everything else as an asset', () => {
    expect(accountKind(acct({ classification: 'asset' }))).toBe('asset')
  })
})

describe('parseSidebarLocation', () => {
  it('reads an account register', () => {
    expect(parseSidebarLocation('/accounts/abc-123')).toEqual({ kind: 'account', id: 'abc-123' })
  })

  it('reads a liability page', () => {
    expect(parseSidebarLocation('/liabilities/l-9')).toEqual({ kind: 'liability', id: 'l-9' })
  })

  it('highlights nothing on the accounts overview', () => {
    // `/accounts` is the list of them all. Matching a prefix here would light
    // every row at once.
    expect(parseSidebarLocation('/accounts')).toBeNull()
    expect(parseSidebarLocation('/liabilities')).toBeNull()
  })

  it('highlights nothing on unrelated pages', () => {
    expect(parseSidebarLocation('/budget')).toBeNull()
    expect(parseSidebarLocation('/reports')).toBeNull()
    expect(parseSidebarLocation('/')).toBeNull()
  })

  it('tolerates a trailing slash', () => {
    expect(parseSidebarLocation('/accounts/abc-123/')).toEqual({ kind: 'account', id: 'abc-123' })
  })

  it('decodes an escaped id', () => {
    expect(parseSidebarLocation('/accounts/a%20b')).toEqual({ kind: 'account', id: 'a b' })
  })
})

describe('isRowActive', () => {
  const onAccount = (id: string) => parseSidebarLocation(`/accounts/${id}`)
  const onLiability = (id: string) => parseSidebarLocation(`/liabilities/${id}`)

  it('lights the account row whose register is open', () => {
    expect(isRowActive(accountTarget('a1'), null, onAccount('a1'))).toBe(true)
    expect(isRowActive(accountTarget('a2'), null, onAccount('a1'))).toBe(false)
  })

  it('lights the liability row whose page is open', () => {
    const target = { kind: 'liability', liabilityId: 'l1' } as const
    expect(isRowActive(target, null, onLiability('l1'))).toBe(true)
    expect(isRowActive(target, null, onLiability('l2'))).toBe(false)
  })

  // The divergence a per-section rule would have got wrong: a managed
  // liability is reachable two ways, and the register shortcut on its own row
  // is one of them.
  it('lights a managed liability row from the register its shortcut opens', () => {
    const target = { kind: 'liability', liabilityId: 'l1' } as const
    expect(isRowActive(target, 'a1', onAccount('a1'))).toBe(true)
  })

  it('does not light a liability row from someone else’s register', () => {
    const target = { kind: 'liability', liabilityId: 'l1' } as const
    expect(isRowActive(target, 'a1', onAccount('a2'))).toBe(false)
  })

  it('never confuses an account id with a liability id', () => {
    // Both tables are UUIDs, but nothing stops them colliding in a fixture —
    // and a row must answer to its own kind of page only.
    expect(isRowActive(accountTarget('same'), null, onLiability('same'))).toBe(false)
    expect(
      isRowActive({ kind: 'liability', liabilityId: 'same' }, null, onAccount('same'))
    ).toBe(false)
  })

  it('lights nothing when the URL names no account or liability', () => {
    expect(isRowActive(accountTarget('a1'), null, parseSidebarLocation('/budget'))).toBe(false)
    expect(
      isRowActive({ kind: 'liability', liabilityId: 'l1' }, 'a1', parseSidebarLocation('/accounts'))
    ).toBe(false)
  })

  it('lights an unmanaged liability row rendered from its own account', () => {
    // An off-budget liability account with no tracker targets the account.
    expect(isRowActive({ kind: 'account', accountId: 'a7' }, null, onAccount('a7'))).toBe(true)
  })

  it('agrees with the rows buildLiabilityRows actually produces', () => {
    // Ties the rule to the real row shape rather than to hand-built targets:
    // a managed off-budget loan lights up from both of its pages.
    const account = acct({ id: 'acct-loan', on_budget: false, classification: 'liability' })
    const tracker = liab({ id: 'liab-loan', linked_account_id: 'acct-loan', current_balance: 900 })
    const [row] = buildLiabilityRows([account], [tracker])

    expect(isRowActive(row.target, row.registerAccountId, onLiability('liab-loan'))).toBe(true)
    expect(isRowActive(row.target, row.registerAccountId, onAccount('acct-loan'))).toBe(true)
    expect(isRowActive(row.target, row.registerAccountId, onAccount('acct-other'))).toBe(false)
  })
})
