/**
 * Every surface that quotes the emergency fund says the same thing about what
 * it counted, and opens the same picker — from one mocked `useEmergencyFund`.
 *
 * The Essentials report, the Emergency Fund report and the Guide's sizer show
 * the Counting line; Settings → Tags opens the picker from the Emergency fund
 * row; the Guide's signal editor opens it directly.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConceptInfo } from '../../api/guide'
import { useAppStore } from '../../stores/appStore'
import { FUND_COUNTING_LINE } from '../../test-utils/emergencyFundFixtures'

vi.mock('../../api/emergencyFund', async () => {
  const f = await import('../../test-utils/emergencyFundFixtures')
  return {
    useEmergencyFund: () => ({ data: f.FUND_PICKER, isError: false }),
    useSetEmergencyFund: () => ({ mutateAsync: vi.fn(), isPending: false }),
  }
})
vi.mock('../../api/tags', async () => {
  const f = await import('../../test-utils/emergencyFundFixtures')
  return {
    useTags: () => ({ data: [f.EMERGENCY_FUND_TAG], isLoading: false }),
    useTagMembership: () => ({ data: f.FUND_MEMBERSHIP, isError: false }),
    useSetTagMembership: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useTagNotices: () => ({ data: [] }),
    useDismissTagNotice: () => ({ mutate: vi.fn() }),
    useCreateTag: () => ({ mutateAsync: vi.fn() }),
    useUpdateTag: () => ({ mutateAsync: vi.fn() }),
    useDeleteTag: () => ({ mutateAsync: vi.fn() }),
  }
})
vi.mock('../../api/guide', () => ({
  useSetBinding: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useGuideOverview: () => ({ data: undefined }),
  useEmergencyFundPlan: () => ({
    data: {
      months: 3,
      monthly_contribution: 0,
      essentials: { as_paid: 1000, spread: 1000, spread_on: true, monthly: 1000 },
      current: 9400,
      target: 3000,
      gap: 0,
      months_to_fund: 0,
      funded_by: null,
    },
  }),
}))

const FUND = {
  set_up: true,
  total: 9400,
  categories: [],
  accounts: [],
  external: { declared: false, amount: null, as_of: null, note: null },
}
vi.mock('../../api/reports', () => ({
  useReportRange: () => ({ data: undefined }),
  useReportSettings: () => ({ data: { spread_sinking_funds: true } }),
  useSetReportSettings: () => ({ mutate: vi.fn(), isPending: false }),
  useEssentialsReport: () => ({
    isLoading: false,
    isError: false,
    data: {
      tagged: true,
      months: 12,
      window_start: '2025-09-01',
      window_end: '2026-08-31',
      essentials: { as_paid: 1000, spread: 1000, spread_on: true, monthly: 1000 },
      monthly_total_average: 1000,
      categories: [],
      monthly_series: [],
      reserve: [],
      roadmap_range: [3, 6],
      emergency_fund: FUND,
      runway_months: 9.4,
      class_excluded: [],
    },
  }),
  useEmergencyCoverageReport: () => ({
    isLoading: false,
    isError: false,
    data: {
      months: 12,
      tagged: true,
      fund: FUND,
      coverage_months: 9.4,
      essentials: { as_paid: 1000, spread: 1000, spread_on: true, monthly: 1000 },
      target_low: 3000,
      target_high: 6000,
      target_range: [3, 6],
      series: [],
      external_amount: null,
      external_as_of: null,
      current_month: '2026-09-01',
    },
  }),
}))
vi.mock('../../api/payees', () => ({ usePayees: () => ({ data: undefined }) }))
vi.mock('../../api/budgets', () => ({ useBudgetMonth: () => ({ data: undefined }) }))
vi.mock('../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: undefined }) }))

import { EssentialsReport } from '../reports/charts/EssentialsReport'
import { EmergencyCoverageReport } from '../reports/charts/EmergencyCoverageReport'
import { EmergencyFundSizer } from '../guide/tools/EmergencyFundSizer'
import { TagsPanel } from '../settings/TagsPanel/TagsPanel'
import { SignalEditor } from '../guide/SignalEditor'
import { PICKER_TITLE } from './EmergencyFundPicker'

const EF_CONCEPT: ConceptInfo = {
  key: 'emergency_fund',
  label: 'Emergency fund',
  kind: 'amount',
  binds_to: [],
  prompt: '',
  caveat: '',
  auto: true,
  allows_external: true,
  us_only: false,
  aliases: [],
}

function show(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

async function expectPicker() {
  expect(await screen.findByText(PICKER_TITLE)).toBeInTheDocument()
  // The picker the fixture seeds: the chosen account is checked.
  expect(screen.getByRole('checkbox', { name: /Harborstone Reserve/ })).toBeChecked()
}

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  useAppStore.setState({ currentBudgetId: 'b1', privacyMode: false })
})

const COUNTING_SURFACES: [string, () => ReactElement][] = [
  ['the Essentials report', () => <EssentialsReport budgetId="b1" />],
  ['the Emergency Fund report', () => <EmergencyCoverageReport budgetId="b1" />],
  ['the Guide’s sizer', () => <EmergencyFundSizer />],
]

describe('one Counting line, one picker', () => {
  it.each(COUNTING_SURFACES)('%s shows the Counting line and opens the picker', async (_, ui) => {
    show(ui())
    expect(screen.getByText(FUND_COUNTING_LINE)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))
    await expectPicker()
  })

  it('Settings → Tags opens the picker from the Emergency fund row', async () => {
    show(<TagsPanel budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: /tagged Emergency fund/ }))
    await expectPicker()
  })

  it('the Guide’s signal editor opens the picker for the emergency fund', async () => {
    show(<SignalEditor budgetId="b1" concept={EF_CONCEPT} signal={undefined} onClose={vi.fn()} />)
    await expectPicker()
    expect(
      screen.getByRole('button', { name: 'Don’t track this in the Guide' })
    ).toBeInTheDocument()
  })
})
