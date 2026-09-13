import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { ReportsMobileChrome } from './ReportsMobileChrome'
import { useReportStore } from '../../stores/reportStore'

vi.mock('../../hooks/useMediaQuery', () => ({ useIsMobile: () => true, useIsTouch: () => true }))
vi.mock('./ReportFilters/ReportFiltersBar', () => ({
  ReportFiltersContent: () => <div data-testid="filters-content" />,
}))

describe('ReportsMobileChrome', () => {
  beforeEach(async () => {
    // Drain the previous test's overlay history pops before resetting it.
    await new Promise((r) => setTimeout(r, 0))
    await new Promise((r) => setTimeout(r, 0))
    window.history.replaceState(null, '')
    window.matchMedia ??= (() => ({ matches: false })) as unknown as typeof window.matchMedia
    window.history.replaceState(null, '', '/reports')
    useReportStore.setState({ activeTab: 'spending-trends', navFavorites: false })
    useReportStore.getState().resetFilters()
  })

  it('names the active report and counts the filters in force', () => {
    useReportStore.getState().setFilters({ categoryIds: ['c1'], payeeIds: ['p1'] })
    render(
      <ReportsMobileChrome budgetId="b1" starred={[]} onToggleStar={() => {}} starPending={false} />
    )
    expect(screen.getByRole('button', { name: /Spending Trends/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filters/ }).textContent).toContain('2')
  })

  it('offers no Filters chip on a report that takes no scope', () => {
    useReportStore.setState({ activeTab: 'net-worth' })
    render(
      <ReportsMobileChrome budgetId="b1" starred={[]} onToggleStar={() => {}} starPending={false} />
    )
    expect(screen.queryByRole('button', { name: /Filters/ })).toBeNull()
  })

  it('picks a report from the sheet, grouped by section', async () => {
    render(
      <ReportsMobileChrome budgetId="b1" starred={[]} onToggleStar={() => {}} starPending={false} />
    )
    fireEvent.click(screen.getByRole('button', { name: /Spending Trends/ }))
    expect(screen.getByRole('dialog', { name: 'Reports' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Savings Rate/ }))
    expect(useReportStore.getState().activeTab).toBe('savings-rate')
  })

  it('opens the filters in a sheet with a Done button', () => {
    render(
      <ReportsMobileChrome budgetId="b1" starred={[]} onToggleStar={() => {}} starPending={false} />
    )
    fireEvent.click(screen.getByRole('button', { name: /Filters/ }))
    expect(screen.getByRole('dialog', { name: 'Filters' })).toBeInTheDocument()
    expect(screen.getByTestId('filters-content')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
  })

  it('opens the reports overview beside the star, and picks a report from it', () => {
    render(
      <ReportsMobileChrome budgetId="b1" starred={[]} onToggleStar={() => {}} starPending={false} />
    )
    fireEvent.click(screen.getByRole('button', { name: 'About these reports' }))
    const sheet = screen.getByRole('dialog', { name: 'About these reports' })
    expect(within(sheet).getByRole('heading', { name: 'Cash Flow' })).toBeInTheDocument()
    fireEvent.click(within(sheet).getByRole('button', { name: 'Burn Rate' }))
    expect(useReportStore.getState().activeTab).toBe('burn-rate')
    expect(screen.queryByRole('dialog', { name: 'About these reports' })).toBeNull()
  })

  it('stars the report you are reading', () => {
    const onToggleStar = vi.fn()
    render(
      <ReportsMobileChrome
        budgetId="b1"
        starred={['spending-trends']}
        onToggleStar={onToggleStar}
        starPending={false}
      />
    )
    const star = screen.getByRole('button', { name: 'Remove from favorites' })
    fireEvent.click(star)
    expect(onToggleStar).toHaveBeenCalledOnce()
  })
})
