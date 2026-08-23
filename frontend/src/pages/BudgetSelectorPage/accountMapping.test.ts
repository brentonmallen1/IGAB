/**
 * The mapping step's judgement calls.
 *
 * Context for the thresholds: a real 47-account export gave four assets debt
 * types — a $1.2M house, a $143K property, two vehicles — which subtracted
 * ~$2.8M from net worth and spawned four phantom liabilities. The suggester
 * had all four right and flagged them for review. Nothing objected when they
 * were overridden, which is what `balanceWarning` is for.
 */
import { describe, expect, it } from 'vitest'
import {
  activityLabel,
  classificationWarning,
  choiceForDisposition,
  dispositionOf,
  dormantOpenCount,
  groupAccounts,
  isDormant,
} from './accountMapping'
import type { YnabAccountPreview, YnabAccountTypeChoice } from '../../api/budgets'

const A_YEAR_AGO = '2025-08-01'

function preview(over: Partial<YnabAccountPreview> = {}): YnabAccountPreview {
  return {
    name: 'Checking',
    transaction_count: 10,
    suggested_type: 'checking',
    suggested_on_budget: true,
    needs_review: false,
    implied_balance: '100.00',
    first_activity: '2020-01-01',
    last_activity: '2026-08-01',
    related_group: null,
    ...over,
  }
}

describe('disposition', () => {
  it('defaults to importing', () => {
    expect(dispositionOf(undefined)).toBe('import')
    expect(dispositionOf({ account_type: 'checking', on_budget: true })).toBe('import')
  })

  it('reads skip and close off the choice', () => {
    const base = { account_type: 'checking', on_budget: true }
    expect(dispositionOf({ ...base, skip: true })).toBe('skip')
    expect(dispositionOf({ ...base, close: true })).toBe('close')
  })

  it('lets skip win when both are set, matching the backend', () => {
    // A skipped account is never created, so there is nothing left to close.
    const base = { account_type: 'checking', on_budget: true }
    expect(dispositionOf({ ...base, skip: true, close: true })).toBe('skip')
  })

  it('always writes both flags, so switching back really clears the other', () => {
    // The bug this prevents: pick "import & close", change your mind, pick
    // "import" — and the account still arrives closed because `close` was
    // left behind.
    expect(choiceForDisposition('import')).toEqual({ skip: false, close: false })
    expect(choiceForDisposition('close')).toEqual({ skip: false, close: true })
    expect(choiceForDisposition('skip')).toEqual({ skip: true, close: false })
  })
})

describe('dormancy', () => {
  it('flags an account that has not moved in over a year', () => {
    expect(isDormant('2019-04-02', A_YEAR_AGO)).toBe(true)
  })

  it('leaves a recently used account alone', () => {
    expect(isDormant('2026-08-01', A_YEAR_AGO)).toBe(false)
  })

  it('does not flag an account with no activity at all', () => {
    // Nothing to be dormant *since*. An empty account is a different problem
    // and guessing here would put a "nothing since undefined" note on screen.
    expect(isDormant(null, A_YEAR_AGO)).toBe(false)
  })

  it('is exclusive at the boundary, so the cutoff month itself counts as live', () => {
    expect(isDormant(A_YEAR_AGO, A_YEAR_AGO)).toBe(false)
  })

  it('counts only the dormant accounts still set to plain import', () => {
    // What the bulk offer is keyed on: once an account is already marked
    // "import & close" it must drop out of the count, or the line keeps
    // offering to do something that is already done.
    const accounts = [
      preview({ name: 'Old A', last_activity: '2019-01-01' }),
      preview({ name: 'Old B', last_activity: '2019-01-01' }),
      preview({ name: 'Live', last_activity: '2026-08-01' }),
    ]
    const choices: Record<string, YnabAccountTypeChoice> = {
      'Old B': { account_type: 'savings', on_budget: true, close: true },
    }
    expect(dormantOpenCount(accounts, choices, A_YEAR_AGO)).toBe(1)
  })

  it('drops a dormant account that is being left out entirely', () => {
    const accounts = [preview({ name: 'Old', last_activity: '2019-01-01' })]
    const choices: Record<string, YnabAccountTypeChoice> = {
      Old: { account_type: 'savings', on_budget: true, skip: true },
    }
    expect(dormantOpenCount(accounts, choices, A_YEAR_AGO)).toBe(0)
  })

  it('is zero when nothing is dormant, so the offer stays hidden', () => {
    const accounts = [preview({ last_activity: '2026-08-01' })]
    expect(dormantOpenCount(accounts, {}, A_YEAR_AGO)).toBe(0)
  })
})

describe('classificationWarning', () => {
  it('objects when a debt type is chosen for something we read as an asset', () => {
    // The four real failures: a $1.2M house, a $143K property and two
    // vehicles, all suggested other_asset and all given debt types by hand.
    expect(classificationWarning('asset', 'liability')).toMatch(/debt type, but this reads as/)
  })

  it('objects the other way too', () => {
    expect(classificationWarning('liability', 'asset')).toMatch(/asset type, but this reads as/)
  })

  it('stays quiet when the choice agrees with the suggestion', () => {
    // Which is every row the user never touches — the property that keeps
    // this warning worth reading.
    expect(classificationWarning('asset', 'asset')).toBeNull()
    expect(classificationWarning('liability', 'liability')).toBeNull()
  })

  it('says nothing when either classification is unknown', () => {
    expect(classificationWarning(undefined, 'liability')).toBeNull()
    expect(classificationWarning('asset', undefined)).toBeNull()
  })

  it('is not keyed on the balance, which a YNAB export cannot supply', () => {
    // The design point. `implied_balance` is the sum of the register, and a
    // date-filtered export has no starting-balance rows, so a checking
    // account can legitimately sum to -$14,335. Keying on that sign fired on
    // ten of forty-seven correctly-typed accounts in the real export.
    // Keeping a correct type is silent whatever the balance says.
    expect(classificationWarning('asset', 'asset')).toBeNull()
    expect(classificationWarning('liability', 'liability')).toBeNull()
  })
})

describe('activityLabel', () => {
  it('reads as a month, which is the right precision for "when did this last move"', () => {
    expect(activityLabel('2019-03-04')).toBe('Mar 2019')
  })

  it('says nothing when there is no activity', () => {
    expect(activityLabel(null)).toBeNull()
  })
})

describe('groupAccounts', () => {
  const a = (name: string, related_group: string | null = null) => preview({ name, related_group })

  it('captions a family and leaves the rest alone', () => {
    const sections = groupAccounts([
      a('Apple Wallet'),
      a('Redwood', 'Redwood'),
      a('Redwood CC', 'Redwood'),
      a('TreasuryDirect'),
    ])
    expect(sections.map((s) => s.label)).toEqual([null, 'Redwood', null])
    expect(sections[1].accounts.map((x) => x.name)).toEqual(['Redwood', 'Redwood CC'])
  })

  it('keeps the alphabetical order it was given', () => {
    // Bucketing would hoist Apple Wallet and TreasuryDirect together and put
    // the families after them, which is harder to scan, not easier.
    const sections = groupAccounts([
      a('Apple Wallet'),
      a('Vehicle A', 'Vehicle A'),
      a('Vehicle A Loan', 'Vehicle A'),
      a('Vehicle B', 'Vehicle B'),
      a('Vehicle B Loan', 'Vehicle B'),
    ])
    expect(sections.flatMap((s) => s.accounts.map((x) => x.name))).toEqual([
      'Apple Wallet',
      'Vehicle A',
      'Vehicle A Loan',
      'Vehicle B',
      'Vehicle B Loan',
    ])
  })

  it('does not merge two families that sit next to each other', () => {
    const sections = groupAccounts([
      a('Vehicle A', 'Vehicle A'),
      a('Vehicle A Loan', 'Vehicle A'),
      a('Vehicle B', 'Vehicle B'),
    ])
    expect(sections.map((s) => s.label)).toEqual(['Vehicle A', 'Vehicle B'])
  })

  it('handles an empty preview', () => {
    expect(groupAccounts([])).toEqual([])
  })
})
