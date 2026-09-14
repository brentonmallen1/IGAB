import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EmergencyFundResponse } from '../../../api/guide'

const plan = vi.hoisted(() => ({ data: undefined as unknown }))

vi.mock('../../../api/guide', () => ({
  useGuideOverview: () => ({ data: undefined }),
  useEmergencyFundPlan: () => ({ data: plan.data }),
}))
vi.mock('../../../api/reports', () => ({
  useReportSettings: () => ({ data: { spread_sinking_funds: true } }),
  useSetReportSettings: () => ({ mutate: vi.fn(), isPending: false }),
}))

import { useAppStore } from '../../../stores/appStore'
import { EmergencyFundSizer } from './EmergencyFundSizer'

const response = (over: Partial<EmergencyFundResponse>): EmergencyFundResponse => ({
  months: 3,
  monthly_contribution: 0,
  essentials_monthly: 2200,
  essentials: { as_paid: 2800, spread: 2200, spread_on: true, monthly: 2200 },
  current: 1000,
  target: 6600,
  gap: 5600,
  months_to_fund: null,
  funded_by: null,
  ...over,
})

const renderSizer = () =>
  render(
    <MemoryRouter>
      <EmergencyFundSizer />
    </MemoryRouter>
  )

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
})

describe('EmergencyFundSizer essentials', () => {
  it('reads the figure the setting picks and names the other beside it', () => {
    plan.data = response({})
    renderSizer()
    const essentials = screen.getByText('Essential spending, per month').nextElementSibling
    expect(essentials).toHaveTextContent('$2,200.00 ($2,200.00/mo spread · $2,800.00/mo as paid)')
    expect(
      screen.getByRole('checkbox', { name: 'Spread yearly bills over 12 months' })
    ).toBeChecked()
  })

  it('shows one figure when the two agree', () => {
    plan.data = response({
      essentials_monthly: 2000,
      essentials: { as_paid: 2000, spread: 2000, spread_on: true, monthly: 2000 },
    })
    renderSizer()
    const essentials = screen.getByText('Essential spending, per month').nextElementSibling
    expect(essentials).toHaveTextContent(/^\$2,000\.00$/)
  })

  it('asks for Essential tags when there is no figure', () => {
    plan.data = response({ essentials_monthly: null, essentials: null, target: null, gap: null })
    renderSizer()
    expect(screen.getByText(/tag what you could not do without as Essential/)).toBeInTheDocument()
  })
})
