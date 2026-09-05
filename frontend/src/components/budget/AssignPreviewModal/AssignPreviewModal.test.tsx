/**
 * What a strategy preview promises before you spend real money on it.
 *
 * Two of the strategies SET assigned to a past figure (the history ones) or to
 * zero (Reset Assigned), which unfunds money already spent from an envelope.
 * That is what they are for — and a table of assigned-before/assigned-after is
 * the one place the consequence does not appear, so the preview says it.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { AssignPreviewResponse } from '../../../api/assign'

const preview = vi.hoisted(() => ({ current: null as AssignPreviewResponse | null }))

vi.mock('../../../api/assign', () => ({
  useAssignPreview: () => ({ data: preview.current, isLoading: false }),
  useAssignApply: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../utils/toastUndo', () => ({ useToastUndo: () => vi.fn() }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))

import { AssignPreviewModal } from './AssignPreviewModal'

beforeEach(() => {
  preview.current = {
    strategy: 'reset_assigned',
    items: [
      {
        category_id: 'c1',
        category_name: 'Groceries',
        current_assigned: 150,
        delta: -150,
        new_assigned: 0,
      },
    ],
    total_needed: null,
    to_assign: 0,
    to_return: 150,
    tba_before: 850,
    tba_after: 1000,
    newly_overspent_count: 0,
    newly_overspent_total: 0,
  } as AssignPreviewResponse
})

function open() {
  return render(
    <AssignPreviewModal
      budgetId="b1"
      month="2026-08-01"
      strategy="reset_assigned"
      onClose={vi.fn()}
    />
  )
}

describe('AssignPreviewModal', () => {
  it('says nothing when no envelope ends up in the red', () => {
    open()
    expect(screen.queryByText(/overspent by/)).not.toBeInTheDocument()
  })

  it('names how many envelopes it would push into the red, and by how much', () => {
    preview.current = { ...preview.current!, newly_overspent_count: 1, newly_overspent_total: 130 }
    open()
    expect(screen.getByText(/1 category/)).toBeInTheDocument()
    expect(screen.getByText(/\$130\.00/)).toBeInTheDocument()
    expect(screen.getByText(/Cover Overspending can put it back/)).toBeInTheDocument()
  })

  it('pluralises the count', () => {
    preview.current = { ...preview.current!, newly_overspent_count: 3, newly_overspent_total: 90 }
    open()
    expect(screen.getByText(/3 categories/)).toBeInTheDocument()
  })

  it('keeps the negative-TBA warning separate — different problem, louder tone', () => {
    preview.current = {
      ...preview.current!,
      tba_after: -25,
      newly_overspent_count: 1,
      newly_overspent_total: 130,
    }
    open()
    expect(screen.getByText(/Ready to Assign will go negative/)).toBeInTheDocument()
    expect(screen.getByText(/overspent by/)).toBeInTheDocument()
  })
})
