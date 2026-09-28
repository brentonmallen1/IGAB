import { describe, expect, it } from 'vitest'
import type { SubscriptionCategory, SubscriptionsSummary } from '../../../types'
import {
  activeCard,
  annualSub,
  basisNote,
  cadenceLabel,
  serviceDrill,
  subscriptionTrendRows,
} from './subscriptionsView'
import { OTHER_KEY, stackTrends } from './spendingTrends'

const summary: SubscriptionsSummary = {
  total_annual: 600,
  total_monthly: 50,
  charged_categories: 2,
  tagged_categories: 8,
  new_this_month: 1,
  projected_services: 2,
  stopped_services: 1,
}

function category(id: string, total: number, monthly: number[]): SubscriptionCategory {
  return {
    category_id: id,
    category_name: `Cat ${id}`,
    group_name: 'Bills',
    annual: total,
    monthly: total / 12,
    monthly_amounts: monthly,
    total,
    last_charge_date: '2026-08-05',
    services: [],
  }
}

describe('activeCard', () => {
  it('says N of M tagged categories, and what is new', () => {
    // "Active 2" counted categories under a label that read as services.
    expect(activeCard(summary)).toEqual({
      value: '2 of 8',
      sub: 'tagged categories charged · 1 new this month',
    })
  })

  it('leaves out "0 new this month"', () => {
    expect(activeCard({ ...summary, new_this_month: 0 }).sub).toBe('tagged categories charged')
  })
})

describe('annualSub', () => {
  it('names the year and what in it is projected or left out', () => {
    expect(annualSub(summary)).toBe('last 12 complete months · 2 projected · 1 stopped, left out')
  })

  it('is the year alone when every figure is measured', () => {
    expect(annualSub({ ...summary, projected_services: 0, stopped_services: 0 })).toBe(
      'last 12 complete months'
    )
  })
})

describe('cadenceLabel', () => {
  it.each([
    [{ cadence: 'monthly', interval_days: 31, cadence_assumed: false }, 'monthly'],
    [{ cadence: 'yearly', interval_days: 365, cadence_assumed: false }, 'yearly'],
    [{ cadence: 'days', interval_days: 91, cadence_assumed: false }, 'every 91 days'],
    // One charge: the page must not claim a cadence it never saw.
    [{ cadence: 'monthly', interval_days: 30, cadence_assumed: true }, 'unknown'],
  ] as const)('%o reads %s', (s, label) => {
    expect(cadenceLabel(s)).toBe(label)
  })
})

describe('basisNote', () => {
  it('marks projected and stopped services, and nothing else', () => {
    const note = (
      basis: 'observed' | 'new' | 'price_change' | 'stopped',
      cadence_assumed = false
    ) => basisNote({ basis, cadence_assumed })
    expect(note('new')).toBe('new · projected')
    // One charge is counted once, not projected — the note must not say it was.
    expect(note('new', true)).toBe('new · 1 charge')
    expect(note('price_change')).toBe('new price · projected')
    expect(note('stopped')).toBe('stopped')
    expect(note('observed')).toBeNull()
  })
})

describe('the chart stacks ten categories and an Other band', () => {
  it('stands every bar at the served monthly total', () => {
    // The chart stacked the ten largest and nothing else, so a budget with a
    // dozen tagged categories drew bars short of the month.
    const cats = Array.from({ length: 12 }, (_, i) => category(`c${i}`, 120 - i, [10, 0]))
    const report = { months: ['2026-07-01', '2026-08-01'], monthly_totals: [120, 0] }
    const { rows, series } = stackTrends(report, subscriptionTrendRows(cats), (m) => m)

    expect(series).toHaveLength(11)
    expect(series.at(-1)?.key).toBe(OTHER_KEY)
    expect(rows[0][OTHER_KEY]).toBe(20)
    const drawn = series.reduce((sum, s) => sum + Number(rows[0][s.key] ?? 0), 0)
    expect(drawn).toBe(120)
  })

  it('orders series by what the range charged', () => {
    const rows = subscriptionTrendRows([category('a', 10, [10]), category('b', 30, [30])])
    expect(rows.map((r) => r.key)).toEqual(['b', 'a'])
  })
})

describe('serviceDrill', () => {
  const report = { months: ['2025-10-01'], year_start: '2025-09-01', year_end: '2026-08-31' }

  it('lists the payee inside its category, refunds included, over the year', () => {
    const drill = serviceDrill(
      { category_id: 'c1', category_name: 'Streaming' },
      { payee_id: 'p1', payee_name: 'Northstar Stream', last_charge_date: '2026-09-05' },
      report
    )
    expect(drill).toEqual({
      kind: 'payee',
      label: 'Northstar Stream · Streaming',
      scope: 'leaf',
      categoryIds: ['c1'],
      payeeIds: ['p1'],
      // No direction: a refund is netted into the line, so it is listed too.
      startDate: '2025-09-01',
      // Through this month's charge, which the latest-charge column reads.
      endDate: '2026-09-05',
    })
  })

  it('reaches back to the chart when the range is longer than the year', () => {
    const drill = serviceDrill(
      { category_id: 'c1', category_name: 'Streaming' },
      { payee_id: 'p1', payee_name: 'X', last_charge_date: '2026-03-05' },
      { ...report, months: ['2024-09-01'] }
    )
    expect(drill?.startDate).toBe('2024-09-01')
    expect(drill?.endDate).toBe('2026-08-31')
  })

  it('offers no drill for a service with no payee', () => {
    // A category-wide list would claim other services' charges.
    expect(
      serviceDrill(
        { category_id: 'c1', category_name: 'Streaming' },
        { payee_id: null, payee_name: 'No payee', last_charge_date: '2026-08-05' },
        report
      )
    ).toBeNull()
  })
})
