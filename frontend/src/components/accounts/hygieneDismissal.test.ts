import { describe, expect, it } from 'vitest'

import type { FindingItem, HygieneFinding } from '../../api/accounts'
import { dismissalKeys, isDismissed } from './hygieneDismissal'

function row(id: string): FindingItem {
  return {
    label: 'Harborstone Inn',
    amount: '-120.0000',
    month: null,
    day: '2026-09-14',
    note: null,
    account_id: 'a1',
    transaction_id: id,
    transaction_ids: [],
  }
}

function finding(kind: string, items: FindingItem[] = []): HygieneFinding {
  return {
    kind,
    title: 't',
    summary: 's',
    action: 'a',
    items,
    why: null,
    account_ids: [],
    asset_ids: [],
    transaction_count: items.length,
  }
}

describe('hygiene dismissal', () => {
  it('dismisses an ordinary finding by its kind', () => {
    const f = finding('dormant_open_account', [row('x')])
    expect(dismissalKeys(f)).toEqual(['dormant_open_account'])
    expect(isDismissed(f, ['dormant_open_account'])).toBe(true)
  })

  it('dismisses rows the bank stopped reporting row by row', () => {
    const f = finding('no_longer_at_bank', [row('t1'), row('t2')])
    expect(dismissalKeys(f)).toEqual(['no_longer_at_bank:t1', 'no_longer_at_bank:t2'])
    expect(isDismissed(f, ['no_longer_at_bank'])).toBe(false)
  })

  it('brings the finding back whole when a new row appears', () => {
    const dismissed = dismissalKeys(finding('no_longer_at_bank', [row('t1')]))
    expect(isDismissed(finding('no_longer_at_bank', [row('t1'), row('t2')]), dismissed)).toBe(false)
  })

  it('stays hidden when a dismissed row is resolved and the rest were dismissed too', () => {
    const dismissed = dismissalKeys(finding('no_longer_at_bank', [row('t1'), row('t2')]))
    expect(isDismissed(finding('no_longer_at_bank', [row('t2')]), dismissed)).toBe(true)
  })
})
