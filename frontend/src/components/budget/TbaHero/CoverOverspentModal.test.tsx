/**
 * What the cover dialog promises, and what it says about the card part.
 *
 * The report: "I covered the overspending and some categories are still
 * negative." They were, because the dialog withheld the card-ridden part of
 * each row on the theory that funding it bought nothing. It buys the same
 * thing assigning to the card buys, so the whole red is on offer now and
 * "Still red" means what it says.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { CoverOverspentPreviewResponse } from '../../../api/budgets'

const preview = vi.hoisted(() => ({ current: null as CoverOverspentPreviewResponse | null }))

vi.mock('../../../api/budgets', () => ({
  useCoverOverspentPreview: () => ({ data: preview.current, isLoading: false, refetch: vi.fn() }),
  useCoverOverspentApply: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useBudgetMonth: () => ({ data: { cards: [] } }),
}))
vi.mock('../../../utils/toastUndo', () => ({ useUndoToast: () => vi.fn() }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))

import { CoverOverspentModal } from './CoverOverspentModal'

function item(over: Record<string, unknown> = {}) {
  return {
    category_id: 'c1',
    category_name: 'Groceries',
    overspent: 30,
    proposed_addition: 30,
    remaining_after: 0,
    credit_overspent: 0,
    ...over,
  }
}

beforeEach(() => {
  preview.current = {
    items: [item()],
    total_overspent: 30,
    total_overspent_credit: 0,
    total_addition: 30,
    tba_before: 500,
    tba_after: 470,
  } as CoverOverspentPreviewResponse
})

function open() {
  return render(<CoverOverspentModal budgetId="b1" month="2026-08-01" onClose={vi.fn()} />)
}

describe('CoverOverspentModal', () => {
  it('reports nothing left over when the whole red is cash', () => {
    open()
    const cells = screen.getAllByRole('cell')
    expect(cells.at(-1)).toHaveTextContent('$0.00')
    expect(screen.queryByText(/on a card/)).not.toBeInTheDocument()
  })

  it('takes a fully covered row to zero even when part of it rode on a card', () => {
    preview.current = {
      ...preview.current!,
      items: [item({ overspent: 50, proposed_addition: 50, credit_overspent: 20 })],
      total_overspent: 50,
      total_overspent_credit: 20,
    }
    open()

    const cells = screen.getAllByRole('cell')
    expect(cells.at(-1)).toHaveTextContent('$0.00')
    expect(cells.at(-1)).not.toHaveTextContent('-$')
  })

  it('says where the card part of the money goes', () => {
    // Same amount, different destination: into the card's set-aside, not the
    // envelope. That is the one thing a reader cannot infer from the figures.
    preview.current = {
      ...preview.current!,
      items: [item({ overspent: 50, proposed_addition: 50, credit_overspent: 20 })],
      total_overspent_credit: 20,
    }
    open()

    expect(screen.getByText(/\$20\.00\s+retires card debt/)).toBeInTheDocument()
    expect(screen.getByText(/swiped on a card/)).toBeInTheDocument()
  })

  it('never claims to retire more debt than it is assigning', () => {
    // Ready to Assign ran short: 10 of a 50 red, 20 of which was ridden.
    preview.current = {
      ...preview.current!,
      items: [
        item({ overspent: 50, proposed_addition: 10, remaining_after: 40, credit_overspent: 20 }),
      ],
      total_addition: 10,
    }
    open()

    expect(screen.getByText(/\$10\.00\s+retires card debt/)).toBeInTheDocument()
    const cells = screen.getAllByRole('cell')
    expect(cells.at(-1)).toHaveTextContent('-$40.00')
  })
})
