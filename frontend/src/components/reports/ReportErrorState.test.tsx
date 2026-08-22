/**
 * A retry button that can never work is worse than no button: the user presses
 * it, nothing changes, and the app looks broken rather than the request.
 * These pin the distinction the state draws — and the escape hatch it offers
 * when a saved view is the likely cause.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ReportErrorState } from './ReportErrorState'
import { useReportStore } from '../../stores/reportStore'

function httpError(status: number, detail?: unknown) {
  return { response: { status, data: detail === undefined ? {} : { detail } } }
}

beforeEach(() => {
  useReportStore.getState().resetFilters()
  useReportStore.getState().setActiveTab('overview')
})

describe('ReportErrorState', () => {
  it('always offers retry and reports the failure', () => {
    const onRetry = vi.fn()
    render(<ReportErrorState onRetry={onRetry} />)
    expect(screen.getByText("Couldn't load this report.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('stays optimistic when no error is supplied', () => {
    render(<ReportErrorState onRetry={vi.fn()} />)
    expect(screen.queryByText(/fail the same way/)).not.toBeInTheDocument()
  })

  it('treats a dropped connection as worth retrying', () => {
    render(<ReportErrorState onRetry={vi.fn()} error={{ message: 'Network Error' }} />)
    expect(screen.queryByText(/fail the same way/)).not.toBeInTheDocument()
  })

  it.each([502, 503, 504, 408, 429])('treats %i as transient', (status) => {
    render(<ReportErrorState onRetry={vi.fn()} error={httpError(status)} />)
    expect(screen.queryByText(/fail the same way/)).not.toBeInTheDocument()
  })

  it('says so when the server failed deterministically', () => {
    render(<ReportErrorState onRetry={vi.fn()} error={httpError(500)} />)
    expect(screen.getByText(/fail the same way/)).toBeInTheDocument()
  })

  it('shows the server message when there is one worth showing', () => {
    render(
      <ReportErrorState onRetry={vi.fn()} error={httpError(422, 'Unknown group by')} />
    )
    expect(screen.getByText('Unknown group by')).toBeInTheDocument()
  })

  it('swallows FastAPI boilerplate rather than repeating it', () => {
    render(
      <ReportErrorState onRetry={vi.fn()} error={httpError(500, 'Internal Server Error')} />
    )
    expect(screen.queryByText('Internal Server Error')).not.toBeInTheDocument()
  })

  describe('when a saved view is driving the report', () => {
    beforeEach(() => {
      useReportStore.getState().setActiveTab('pareto')
      useReportStore.getState().setFilters({ viewId: 'v1' })
    })

    it('offers clearing the view as the action that can change the outcome', () => {
      render(<ReportErrorState onRetry={vi.fn()} error={httpError(500)} />)
      fireEvent.click(screen.getByRole('button', { name: 'Clear view' }))
      expect(useReportStore.getState().filters.viewId).toBeNull()
    })

    it('does not blame the view for a transient failure', () => {
      render(<ReportErrorState onRetry={vi.fn()} error={httpError(503)} />)
      expect(screen.queryByRole('button', { name: 'Clear view' })).not.toBeInTheDocument()
    })

    it('does not offer it on a tab where views do nothing', () => {
      useReportStore.getState().setActiveTab('net-worth')
      render(<ReportErrorState onRetry={vi.fn()} error={httpError(500)} />)
      expect(screen.queryByRole('button', { name: 'Clear view' })).not.toBeInTheDocument()
    })
  })
})
