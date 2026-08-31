/**
 * The badge's contract: it must still be there when the user comes back.
 * Counting only in-flight jobs made it vanish at exactly the moment a receipt
 * finished — the one moment it had something worth saying.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const counts = vi.hoisted(() => ({ value: { active: 0, needsReview: 0 } }))
vi.mock('../../api/aiJobs', () => ({ useAIJobCounts: () => ({ data: counts.value }) }))
vi.mock('../../stores/appStore', () => ({
  useAppStore: (sel: (s: unknown) => unknown) => sel({ currentBudgetId: 'b1' }),
}))

import { AIActivityBadge } from './AIActivityBadge'

function renderBadge() {
  return render(
    <MemoryRouter>
      <AIActivityBadge />
    </MemoryRouter>
  )
}

describe('AIActivityBadge', () => {
  beforeEach(() => {
    counts.value = { active: 0, needsReview: 0 }
  })

  it('renders nothing when there is no work and nothing to review', () => {
    const { container } = renderBadge()
    expect(container).toBeEmptyDOMElement()
  })

  it('shows in-flight work while jobs are processing', () => {
    counts.value = { active: 2, needsReview: 0 }
    renderBadge()
    expect(screen.getByRole('button', { name: /2 AI jobs processing/ })).toBeInTheDocument()
  })

  it('stays visible once the work finishes and reviews are waiting', () => {
    counts.value = { active: 0, needsReview: 3 }
    renderBadge()
    expect(screen.getByRole('button', { name: '3 AI transactions to review' })).toBeInTheDocument()
  })

  it('prefers the in-flight count when both are non-zero', () => {
    // Transient work wins; the review count is still there once it settles.
    counts.value = { active: 1, needsReview: 5 }
    renderBadge()
    expect(screen.getByRole('button', { name: /1 AI job processing/ })).toBeInTheDocument()
  })

  it('does not pulse when it means "reviews waiting" rather than "working"', () => {
    counts.value = { active: 0, needsReview: 1 }
    const { container } = renderBadge()
    expect(container.querySelector('.ai-activity-badge--review')).not.toBeNull()
  })

  it('singularises', () => {
    counts.value = { active: 0, needsReview: 1 }
    renderBadge()
    expect(screen.getByRole('button', { name: '1 AI transaction to review' })).toBeInTheDocument()
  })
})
