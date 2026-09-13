import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../hooks/useMediaQuery', () => ({ useIsMobile: () => false, useIsTouch: () => false }))
vi.mock('../../api/reportFavorites', () => ({
  useReportFavorites: () => ({ data: [] }),
  useSetReportFavorites: () => ({ mutate: () => {}, isPending: false }),
}))
vi.mock('./ReportFilters/ReportFiltersBar', () => ({ ReportFiltersBar: () => null }))
vi.mock('./DrillDownPanel/DrillDownPanel', () => ({ DrillDownPanel: () => null }))
vi.mock('./charts/WishlistDisciplineReport', () => ({ WishlistDisciplineReport: () => null }))
vi.mock('./charts/NetWorthChart', () => ({ NetWorthReport: () => null }))
vi.mock('./charts/DayOfWeekChart', () => ({ DayPatternsReport: () => null }))

import { ReportsPage } from '../../pages/ReportsPage/ReportsPage'
import { REPORT_TABS, TAB_GROUPS, useReportStore } from '../../stores/reportStore'
import { useAppStore } from '../../stores/appStore'
import { REPORT_CATALOG, REPORT_SECTIONS } from './reportCatalog'
import { SCOPE_COPY } from './reportScope'

function renderPage() {
  render(
    <MemoryRouter>
      <ReportsPage />
    </MemoryRouter>
  )
}

function openOverview() {
  fireEvent.click(screen.getByRole('button', { name: 'About these reports' }))
  return screen.getByRole('dialog', { name: 'About these reports' })
}

describe('ReportsOverviewDialog', () => {
  beforeEach(async () => {
    await new Promise((r) => setTimeout(r, 0))
    await new Promise((r) => setTimeout(r, 0))
    window.history.replaceState(null, '')
    useAppStore.setState({ currentBudgetId: 'b1' })
    useReportStore.setState({ activeTab: 'wishlist', navFavorites: true })
  })

  it('opens from the desktop nav and lists every group and report', () => {
    renderPage()
    const dialog = openOverview()
    for (const group of TAB_GROUPS) {
      expect(within(dialog).getByRole('heading', { name: group.label })).toBeInTheDocument()
    }
    for (const tab of REPORT_TABS) {
      expect(within(dialog).getByRole('button', { name: tab.label })).toBeInTheDocument()
      expect(within(dialog).getByText(REPORT_CATALOG[tab.id].summary)).toBeInTheDocument()
    }
    expect(within(dialog).getByRole('button', { name: 'Payday Effect' })).toBeInTheDocument()
  })

  it('shows the scope sentence the report’s own info note uses', () => {
    renderPage()
    const dialog = openOverview()
    const row = within(dialog).getByRole('button', { name: 'Net Worth' }).closest('tr')!
    expect(row.textContent).toContain(SCOPE_COPY['all-accounts'])
    expect(row.textContent).toContain(REPORT_CATALOG['net-worth'].leavesOut)
  })

  it('switches to a report and closes when its name is picked', () => {
    renderPage()
    const dialog = openOverview()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Net Worth' }))
    expect(useReportStore.getState().activeTab).toBe('net-worth')
    // Its own group row, which always holds it — not the starred row.
    expect(useReportStore.getState().navFavorites).toBe(false)
    expect(screen.queryByRole('dialog', { name: 'About these reports' })).toBeNull()
  })

  it('opens a section’s host tab', () => {
    renderPage()
    const dialog = openOverview()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Payday Effect' }))
    expect(useReportStore.getState().activeTab).toBe(REPORT_SECTIONS['payday-effect'].tab)
  })
})
