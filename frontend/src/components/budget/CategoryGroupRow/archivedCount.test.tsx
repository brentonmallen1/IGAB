/**
 * A group header that draws no rows has to say whether that means *empty* or
 * *nothing here is drawn*.
 *
 * The grid renders no archived envelope, so a group whose categories have all
 * been archived is a heading over nothing — while deleting it opens a dialog
 * naming those categories, and archiving it can be refused by one of their
 * balances. Reported as "I moved the categories out and it still says they are
 * in there": nothing on the page could have told them otherwise.
 *
 * The count is the server's (`archived_category_count`). What is asserted here
 * is that the header shows it, and that it leads somewhere — a number with no
 * way to reach the envelopes it counts is a riddle, not an answer.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { CategoryGroupRow } from './CategoryGroupRow'
import { makeCategory, makeCategoryBalance, makeCategoryGroup } from '../../../test-utils/factories'
import type { CategoryBalance } from '../../../types'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function renderGroup(
  over: { archived?: number; drawn?: number; onShowArchived?: () => void } = {}
) {
  const drawn = over.drawn ?? 0
  const categories = Array.from({ length: drawn }, (_, i) =>
    makeCategory({ id: `c${i}`, name: `Envelope ${i}` })
  )
  const balances = new Map<string, CategoryBalance>(
    categories.map((c) => [c.id, makeCategoryBalance({ category_id: c.id })])
  )
  return render(
    <CategoryGroupRow
      group={makeCategoryGroup({ name: 'Fitness', archived_category_count: over.archived ?? 0 })}
      categories={categories}
      balanceMap={balances}
      budgetId="b1"
      month="2026-09-01"
      index={0}
      onShowArchived={over.onShowArchived}
    />,
    { wrapper }
  )
}

describe('a group holding archived envelopes', () => {
  it('says so, rather than drawing a heading over nothing', () => {
    renderGroup({ archived: 2, drawn: 0 })
    expect(
      screen.getByRole('button', { name: '2 archived categories in Fitness' })
    ).toHaveTextContent('2 archived')
  })

  it('says it in the singular for one', () => {
    renderGroup({ archived: 1, drawn: 0 })
    screen.getByRole('button', { name: '1 archived category in Fitness' })
  })

  it('says it even when the group also draws rows', () => {
    // The delete dialog will name all six; the page should not imply four.
    renderGroup({ archived: 2, drawn: 4 })
    screen.getByRole('button', { name: '2 archived categories in Fitness' })
  })

  it('stays quiet on an ordinary group', () => {
    renderGroup({ archived: 0, drawn: 3 })
    expect(screen.queryByText(/archived/)).toBeNull()
  })

  it('opens the archived envelopes room', async () => {
    const onShowArchived = vi.fn()
    renderGroup({ archived: 2, drawn: 0, onShowArchived })
    await userEvent.click(screen.getByRole('button', { name: '2 archived categories in Fitness' }))
    expect(onShowArchived).toHaveBeenCalledOnce()
  })

  it('still states the count where there is nowhere to send the user', () => {
    // A view renders the budget's groups read-only, and the archived room acts
    // on the default arrangement. The fact is still true there.
    renderGroup({ archived: 2, drawn: 0 })
    expect(screen.getByRole('button', { name: '2 archived categories in Fitness' })).toBeDisabled()
  })
})
