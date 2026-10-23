/**
 * The Income Split page: groups start collapsed, the legend states the
 * distance from the rule, and the states that need care say so.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { IncomeSplitLine, IncomeSplitReport as Report } from '../../../types'

const state = vi.hoisted(() => ({ data: undefined as unknown }))
vi.mock('../../../api/reports', () => ({
  useIncomeSplitReport: () => ({
    data: state.data,
    isLoading: false,
    isError: false,
    error: null,
    refetch: () => {},
  }),
}))
vi.mock('../ReportExportButton/ReportExportButton', () => ({ ReportExportButton: () => null }))

import { IncomeSplitReport } from './IncomeSplitReport'

const line = (over: Partial<IncomeSplitLine>): IncomeSplitLine => ({
  category_id: 'c',
  name: '',
  group_name: 'Everyday',
  reason: 'essential',
  total: 0,
  count: 1,
  spread: false,
  as_paid: null,
  minimum: null,
  above_minimum: null,
  minimum_unknown: false,
  note: null,
  ...over,
})

function report(over: Partial<Report> = {}): Report {
  return {
    start_date: '2026-07-01',
    end_date: '2026-09-30',
    months: 3,
    whole_months: true,
    running: false,
    clamped: false,
    tagged: true,
    spread_on: true,
    income: 21600,
    needs: {
      total: 12528,
      lines: [
        line({ category_id: 'm', name: 'Mortgage', reason: 'essential_debt', total: 6300 }),
        line({
          category_id: 'a',
          name: 'Auto loan',
          reason: 'essential_debt',
          total: 1200,
          minimum: 325,
          above_minimum: 225,
        }),
        line({ category_id: 'g', name: 'Groceries', total: 5028 }),
      ],
    },
    wants: {
      total: 5184,
      committed: [line({ category_id: 'y', name: 'Gym', reason: 'cost_of_living', total: 804 })],
      chosen: [line({ category_id: 'd', name: 'Dining out', reason: 'untagged', total: 4380 })],
    },
    savings_debt: { total: 2592, saved: [], debt: [] },
    uncategorized: { total: 432, count: 12 },
    left_over: 864,
    strict: { needs: 12303, savings_debt: 2817 },
    ...over,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <IncomeSplitReport budgetId="b1" />
    </MemoryRouter>
  )
}

beforeEach(() => {
  state.data = report()
})

describe('IncomeSplitReport', () => {
  it('states each bucket against the rule as a distance', () => {
    renderPage()
    expect(screen.getByText('Rule 50% · 8 pts over')).toBeInTheDocument()
    expect(screen.getByText('Rule 30% · 6 pts under')).toBeInTheDocument()
    expect(screen.getByText('Rule 20% · 8 pts under')).toBeInTheDocument()
  })

  it('says what it replaced', () => {
    renderPage()
    expect(screen.getByText(/Replaces Cost of Living and\s+Discretionary/)).toBeInTheDocument()
  })

  it('starts every group collapsed, and opens one or all on request', () => {
    renderPage()
    expect(screen.queryByText('Mortgage')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Needs/ }))
    expect(screen.getByText('Mortgage')).toBeInTheDocument()
    expect(
      screen.getByText('Minimum $325.00 a month today — $225.00 paid above it')
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    expect(screen.getByText('Dining out')).toBeInTheDocument()
    expect(screen.getByText('Committed, not essential — tagged Cost of living')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }))
    expect(screen.queryByText('Dining out')).toBeNull()
  })

  it("offers the rule's own debt reading under Needs", () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /Needs/ }))
    expect(screen.getByText(/Needs 57% · Savings & debt 13%/)).toBeInTheDocument()
  })

  it('asks for the Essential tag when nothing carries it', () => {
    state.data = report({ tagged: false })
    renderPage()
    expect(screen.getByText(/Choose .* categories in Settings → Tags/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Expand all' })).toBeNull()
  })

  it('holds back the gaps while a quarter of take-home is unfiled', () => {
    state.data = report({ uncategorized: { total: 6480, count: 90 }, left_over: -5184 })
    renderPage()
    expect(screen.getByText(/went out unfiled/)).toBeInTheDocument()
    expect(screen.queryByText(/pts over/)).toBeNull()
  })

  it('says when a range runs to today', () => {
    state.data = report({ running: true, whole_months: false, months: 0.72 })
    renderPage()
    expect(screen.getByText(/Left over reads\s+high until the month is done/)).toBeInTheDocument()
  })
})
