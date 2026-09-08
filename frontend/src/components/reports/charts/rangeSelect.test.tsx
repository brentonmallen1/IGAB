/**
 * The report toolbar's range picker.
 *
 * It was three buttons — 6/12/24 — which is as many windows as a button row
 * holds, and so the horizon stopped at two years however much history a
 * budget had. The options are now derived from the budget's own span, because
 * a 60-month window over 18 months of data draws 42 empty leading months and
 * that reads as data loss, not as an empty window.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const range = vi.hoisted(() => ({ current: null as { months_available: number } | null }))
vi.mock('../../../api/reports', () => ({ useReportRange: () => ({ data: range.current }) }))
vi.mock('../../../stores/appStore', () => ({ useAppStore: () => 'b1' }))

import { ReportRangeSelect, rangeOptions } from './rangeSelect'
import { DEFAULT_RANGE_MONTHS, useReportStore } from '../../../stores/reportStore'

beforeEach(() => useReportStore.setState({ rangeMonths: DEFAULT_RANGE_MONTHS }))

describe('rangeOptions', () => {
  it('offers only windows the budget can fill, and names the longest "All time"', () => {
    expect(rangeOptions(18, 12)).toEqual([
      { months: 3, label: '3 months' },
      { months: 6, label: '6 months' },
      { months: 12, label: '12 months' },
      { months: 18, label: 'All time (18 months)' },
    ])
  })

  it('goes well past two years when the history is there', () => {
    // The whole point of the change: 24 was a ceiling, not a limit.
    expect(rangeOptions(120, 12).map((o) => o.months)).toEqual([3, 6, 12, 24, 36, 48, 60, 120])
  })

  it('never offers a window equal to the span twice', () => {
    // 12 months of history: the ladder's own 12 would duplicate "All time".
    expect(rangeOptions(12, 12).map((o) => o.months)).toEqual([3, 6, 12])
    expect(rangeOptions(12, 12).at(-1)?.label).toBe('All time (12 months)')
  })

  it('collapses to a single option for a brand-new budget', () => {
    expect(rangeOptions(1, 1)).toEqual([{ months: 1, label: 'All time (1 months)' }])
  })

  it('falls back to the plain ladder while the span is unknown', () => {
    // 0 is "not fetched yet" or "no transactions", never "no months to show".
    expect(rangeOptions(0, 12).map((o) => o.months)).toEqual([3, 6, 12, 24, 36, 48, 60])
  })

  it('keeps the current window even when the history no longer justifies it', () => {
    // A select whose value matches no option renders blank, over a chart that
    // is plainly showing something.
    expect(rangeOptions(8, 24).map((o) => o.months)).toEqual([3, 6, 8, 24])
  })
})

describe('ReportRangeSelect', () => {
  it('shows what the budget can offer', () => {
    range.current = { months_available: 30 }
    render(<ReportRangeSelect />)
    expect(screen.getByRole('combobox', { name: 'Date range' })).toHaveValue('12')
    expect(screen.getByRole('option', { name: 'All time (30 months)' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '36 months' })).not.toBeInTheDocument()
  })

  it('records the chosen window as a number, for every report', () => {
    // The store, not a prop: sixteen reports each held this in `useState(12)`,
    // and the tabs are separate components — so the one holding a 6-month
    // choice was unmounted the moment you left it, and the next initialised
    // its own 12.
    range.current = { months_available: 30 }
    return userEvent
      .selectOptions(render(<ReportRangeSelect />).getByRole('combobox'), '24')
      .then(() => expect(useReportStore.getState().rangeMonths).toBe(24))
  })

  it('opens on whatever window was last chosen', () => {
    range.current = { months_available: 30 }
    useReportStore.setState({ rangeMonths: 6 })
    render(<ReportRangeSelect />)
    expect(screen.getByRole('combobox', { name: 'Date range' })).toHaveValue('6')
  })
})
