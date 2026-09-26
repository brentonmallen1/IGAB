/**
 * Every chart that stacks figures that can go below zero stacks by sign.
 *
 * `MIXED_SIGN_STACK` is one constant; what this pins is that each stacked
 * chart spreads it, which no pure test can see. Savings Rate is the chart that
 * did not: a month that drew money back out of savings (Saved negative) drew
 * its positive Debt Paid below zero. The others carried the offset inline,
 * each under its own comment.
 *
 * recharts renders zero-size under jsdom, so the chart containers are stubbed
 * and record the offset they were handed.
 */
import { render } from '@testing-library/react'
import type { ComponentType, ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const offsets = vi.hoisted(() => ({ seen: [] as (string | undefined)[] }))

vi.mock('recharts', () => {
  const container = ({ stackOffset, children }: { stackOffset?: string; children: ReactNode }) => {
    offsets.seen.push(stackOffset)
    return <div>{children}</div>
  }
  const nothing = () => null
  return {
    ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    BarChart: container,
    ComposedChart: container,
    LineChart: container,
    Bar: nothing,
    Area: nothing,
    Line: nothing,
    Cell: nothing,
    Tooltip: nothing,
    Legend: nothing,
    CartesianGrid: nothing,
    ReferenceLine: nothing,
    XAxis: nothing,
    YAxis: nothing,
  }
})

const queryState = vi.hoisted(() => ({ current: { data: undefined as unknown } }))

vi.mock('../../../api/reports', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  const mocked: Record<string, unknown> = {}
  for (const key of Object.keys(actual)) {
    mocked[key] = key.startsWith('use')
      ? () => ({ ...queryState.current, isLoading: false, isError: false, refetch: () => {} })
      : actual[key]
  }
  return mocked
})
vi.mock('../../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: undefined }) }))

import { AccountCompositionReport } from './AccountCompositionChart'
import { CostOfLivingReport } from './CostOfLivingReport'
import { IncomeSourcesReport } from './IncomeSourcesReport'
import { SavingsRateReport } from './SavingsRateChart'

/** Each chart with a month that has a negative segment under a positive one. */
const CASES: [string, ComponentType<{ budgetId: string }>, unknown][] = [
  [
    'Savings Rate — Saved drawn down beside a debt payment',
    SavingsRateReport,
    {
      months: [
        {
          month: '2026-08-01',
          income: 4000,
          spending: 3000,
          savings: -500,
          savings_moved: -500,
          savings_held: 0,
          debt_principal: 400,
          savings_rate: -0.125,
          savings_rate_with_debt: -0.025,
        },
      ],
      start_date: '2026-08-01',
      end_date: '2026-08-31',
      summary: {
        income: 4000,
        spending: 3000,
        savings: -500,
        savings_moved: -500,
        savings_held: 0,
        debt_principal: 400,
        savings_rate: -0.125,
        savings_rate_with_debt: -0.025,
      },
    },
  ],
  [
    'Account Composition — a card balance under checking',
    AccountCompositionReport,
    {
      points: [
        {
          date: '2026-08-31',
          balances: { checking: 3000, credit_card: -1200 },
          net_worth: 1800,
          asset_value_total: 0,
        },
      ],
    },
  ],
  [
    'Income by Source — a clawed-back paycheck',
    IncomeSourcesReport,
    {
      months: ['2026-08-01'],
      sources: [
        { payee_id: 'p1', payee_name: 'Northwind Payserv', monthly: [3000], total: 3000, count: 1 },
        { payee_id: 'p2', payee_name: 'Harborstone', monthly: [-75], total: -75, count: 1 },
      ],
      monthly_totals: [2925],
      total: 2925,
      avg_monthly: 2925,
      months_averaged: 1,
    },
  ],
  [
    'Cost of Living — a group whose refunds beat its spending',
    CostOfLivingReport,
    {
      months: ['2026-08-01'],
      months_averaged: 1,
      window_start: '2026-08-01',
      window_end: '2026-08-31',
      groups: [
        {
          group_name: 'Bills',
          monthly_amounts: [700],
          total: 700,
          avg_monthly: 700,
          share: 100,
          category_ids: ['c1'],
        },
        {
          group_name: 'Health',
          monthly_amounts: [-40],
          total: -40,
          avg_monthly: -40,
          share: 0,
          category_ids: ['c2'],
        },
      ],
      avg_monthly_cost_of_living: 660,
      avg_monthly_essentials: null,
      avg_monthly_income: 1200,
      basis: 'tag',
      tagged: true,
      class_excluded: [],
      counted_classes: ['spending', 'debt_principal'],
    },
  ],
]

beforeEach(() => {
  offsets.seen = []
})

describe('a stack with a negative segment is drawn by sign', () => {
  it.each(CASES)('%s', (_name, Report, data) => {
    queryState.current = { data }
    render(
      <MemoryRouter>
        <Report budgetId="b1" />
      </MemoryRouter>
    )
    expect(offsets.seen.length).toBeGreaterThan(0)
    expect(offsets.seen.every((o) => o === 'sign')).toBe(true)
  })
})
