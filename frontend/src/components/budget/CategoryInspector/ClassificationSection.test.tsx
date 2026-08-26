/**
 * The "Counts as" badge: on the exceptional categories only, with the reason
 * a hover away. An ordinary spending category renders nothing — a chip on
 * every category would say nothing about any of them.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CategoryClassification } from '../../../types'

const classification = vi.hoisted(() => ({ current: undefined as CategoryClassification | undefined }))

vi.mock('../../../api/categories', () => ({
  useCategoryClassification: () => ({ data: classification.current }),
}))

import { ClassificationSection } from './ClassificationSection'
import { TOOLTIP_DELAY_MS } from '../../common/Tooltip/tooltipDelay'

const DEBT: CategoryClassification = {
  classes: [
    { activity_class: 'debt_principal', label: 'Debt payment', total: '275.00', count: 1 },
    { activity_class: 'spending', label: 'Spending', total: '4.50', count: 1 },
  ],
  window_months: 12,
  dominant: 'debt_principal',
  dominant_label: 'Debt payment',
  explanation:
    'Most of this category’s activity in the last 12 months counts as Debt payment in reports, because it pays down a tracked debt.',
}

beforeEach(() => {
  classification.current = DEBT
})

describe('ClassificationSection', () => {
  it('badges a debt-payment category and warns about spending reports', () => {
    render(<ClassificationSection categoryId="c1" />)
    expect(screen.getByText('Counts as')).toBeInTheDocument()
    expect(screen.getByText('Debt payment')).toBeInTheDocument()
    expect(screen.getByText(/Spending reports leave this out/)).toBeInTheDocument()
  })

  it('explains itself on hover, composition included', () => {
    vi.useFakeTimers()
    render(<ClassificationSection categoryId="c1" />)
    fireEvent.mouseEnter(screen.getByText('Debt payment'))
    // Tooltips wait the one shared delay before showing.
    act(() => vi.advanceTimersByTime(TOOLTIP_DELAY_MS))
    vi.useRealTimers()
    expect(screen.getByRole('tooltip')).toHaveTextContent('pays down a tracked debt')
    expect(screen.getByRole('tooltip')).toHaveTextContent('Spending: $4.50')
  })

  it('renders nothing for an ordinary category', () => {
    classification.current = {
      classes: [
        { activity_class: 'spending', label: 'Spending', total: '80.00', count: 4 },
      ],
      window_months: 12,
      dominant: null,
      dominant_label: null,
      explanation: null,
    }
    const { container } = render(<ClassificationSection categoryId="c1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing while loading', () => {
    classification.current = undefined
    const { container } = render(<ClassificationSection categoryId="c1" />)
    expect(container).toBeEmptyDOMElement()
  })
})
