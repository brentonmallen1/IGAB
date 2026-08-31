import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReportRangeButtons } from './rangeButtons'

describe('ReportRangeButtons', () => {
  it('offers 6/12/24 by default — what eight of the nine copies did', () => {
    render(<ReportRangeButtons months={12} onChange={() => {}} />)
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['6mo', '12mo', '24mo'])
  })

  it('takes a different horizon as a parameter, not a second copy', () => {
    // IncomeExpenseChart is the one that legitimately differs. Expressing it
    // here is what keeps it from being a tenth hand-written selector.
    render(<ReportRangeButtons months={12} onChange={() => {}} ranges={[3, 6, 12, 24]} />)
    expect(screen.getAllByRole('button')).toHaveLength(4)
    expect(screen.getByText('3mo')).toBeInTheDocument()
  })

  it('marks only the active range, for the eye and for a screen reader', () => {
    render(<ReportRangeButtons months={24} onChange={() => {}} />)
    const active = screen.getByText('24mo')
    expect(active).toHaveClass('report-btn--active')
    expect(active).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('6mo')).toHaveAttribute('aria-pressed', 'false')
  })

  it('reports the range that was clicked', async () => {
    const onChange = vi.fn()
    render(<ReportRangeButtons months={12} onChange={onChange} />)
    await userEvent.click(screen.getByText('6mo'))
    expect(onChange).toHaveBeenCalledWith(6)
  })
})
