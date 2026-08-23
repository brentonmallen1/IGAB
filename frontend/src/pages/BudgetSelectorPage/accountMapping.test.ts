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
  balanceWarning,
  choiceForDisposition,
  dispositionOf,
  dormantOpenCount,
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
})

describe('balanceWarning', () => {
  it('objects to a debt type holding a large positive balance', () => {
    // The $1.2M house typed as a mortgage.
    expect(balanceWarning('liability', 1219536)).toMatch(/debt type, but the balance is positive/)
  })

  it('objects to an asset type holding a large negative balance', () => {
    expect(balanceWarning('asset', -710000)).toMatch(/asset type, but the balance is negative/)
  })

  it('still objects to a genuinely overpaid loan — it warns, it does not block', () => {
    // Vehicle A Loan really did hold +$6,111. The user must be able to read
    // this and carry on, so it has to be a remark rather than a gate.
    expect(balanceWarning('liability', 6111)).not.toBeNull()
  })

  it('stays quiet on a credit card paid slightly into credit', () => {
    // The false positive that would cost us the warning above: a warning on
    // every paid-off card is one people stop reading.
    expect(balanceWarning('liability', 50)).toBeNull()
  })

  it('stays quiet when the sign agrees', () => {
    expect(balanceWarning('liability', -3410)).toBeNull()
    expect(balanceWarning('asset', 27704)).toBeNull()
  })

  it('stays quiet on a zero balance and on an unknown type', () => {
    expect(balanceWarning('liability', 0)).toBeNull()
    expect(balanceWarning('asset', 0)).toBeNull()
    expect(balanceWarning(undefined, 1219536)).toBeNull()
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
