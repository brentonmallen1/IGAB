import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { AssignAutoTab } from './AssignAutoTab'
import type { AssignStrategyTotalsResponse } from '../../../api/assign'

function totals(overrides: Partial<AssignStrategyTotalsResponse> = {}, underfundedNeeded = 0): AssignStrategyTotalsResponse {
  const strategies = [
    'underfunded', 'last_month_assigned', 'last_month_spent', 'average_assigned', 'average_spent',
    'reduce_overfunded', 'reset_available', 'reset_assigned',
  ].map((strategy) => ({
    strategy,
    total_amount: strategy === 'underfunded' ? underfundedNeeded : 10,
    total_needed: strategy === 'underfunded' ? underfundedNeeded : null,
    affected_count: 1,
    to_assign: 500,
  })) as AssignStrategyTotalsResponse['strategies']
  return { month: '2026-08', tba: 500, total_overspent: 0, strategies, ...overrides }
}

function setup(t: AssignStrategyTotalsResponse, overspentCount = 0) {
  const onCoverOverspent = vi.fn()
  const onPickStrategy = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AssignAutoTab totals={t} isLoading={false} overspentCount={overspentCount} onPickStrategy={onPickStrategy} onCoverOverspent={onCoverOverspent} />
    </QueryClientProvider>
  )
  const rows = screen.getAllByRole('button').filter((b) => b.hasAttribute('data-assign-row'))
  return { rows, onCoverOverspent, onPickStrategy }
}

describe('AssignAutoTab', () => {
  it('leads with Cover Overspending, disabled when nothing is overspent', () => {
    const { rows } = setup(totals())
    expect(rows[0]).toHaveTextContent('Cover Overspending')
    expect(rows[0]).toBeDisabled()
    expect(rows[1]).toHaveTextContent('Underfunded Targets')
    expect(screen.queryByText(/isn't a target shortfall/)).toBeNull()
  })

  it('shows the overspent amount and count, and opens the cover flow', () => {
    const { rows, onCoverOverspent } = setup(totals({ total_overspent: 123.45 }), 3)
    expect(rows[0]).toBeEnabled()
    expect(rows[0]).toHaveTextContent('3 categories')
    expect(rows[0]).toHaveTextContent('123.45')
    fireEvent.click(rows[0])
    expect(onCoverOverspent).toHaveBeenCalledTimes(1)
  })

  it('explains a $0 underfunded row that sits beside overspending', () => {
    setup(totals({ total_overspent: 50 }), 1)
    expect(screen.getByText(/isn't a target shortfall/)).toBeInTheDocument()
  })

  it('does not explain when targets genuinely need money', () => {
    setup(totals({ total_overspent: 50 }, 200), 1)
    expect(screen.queryByText(/isn't a target shortfall/)).toBeNull()
  })
})
