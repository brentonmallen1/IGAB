import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SettleWishDialog } from './SettleWishDialog'
import * as wishlistApi from '../../../api/wishlist'
import * as categoriesApi from '../../../api/categories'
import type { Wish, WishSettlement } from '../../../api/wishlist'

vi.mock('../../../api/wishlist', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/wishlist')>()),
  useSettleWish: vi.fn(),
}))
vi.mock('../../../api/categories', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/categories')>()),
  useCategories: vi.fn(),
  useCategoryGroups: vi.fn(),
}))

const settle = vi.fn()

function wish(settlement: WishSettlement | null, status: 'done' | 'dropped' = 'dropped'): Wish {
  return {
    id: 'w1',
    project_id: null,
    name: 'Bike',
    url: null,
    notes: null,
    cost: 1800,
    priority: 0,
    is_priority: false,
    status,
    funding: {
      mode: 'own',
      category_id: 'c1',
      category_name: 'Bike',
      inherited: false,
      owns_envelope: true,
      target_date: null,
    },
    cooling_until: null,
    cooling: false,
    added_on: '2026-08-01',
    last_affirmed_at: null,
    review_due: false,
    done_at: null,
    dropped_at: '2026-09-20',
    created_at: '2026-08-01T00:00:00Z',
    reach: null,
    settlement,
  }
}

const held = (over: Partial<WishSettlement> = {}): WishSettlement => ({
  category_id: 'c1',
  name: 'Bike',
  available: 400,
  has_goal: true,
  ...over,
})

function renderDialog(w: Wish) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SettleWishDialog budgetId="b1" wish={w} onClose={vi.fn()} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  settle.mockReset()
  settle.mockResolvedValue(wish(null))
  vi.mocked(wishlistApi.useSettleWish).mockReturnValue({
    mutateAsync: settle,
    isPending: false,
  } as never)
  vi.mocked(categoriesApi.useCategories).mockReturnValue({
    data: [
      { id: 'c1', name: 'Bike', category_group_id: 'g1', is_assignable: true },
      { id: 'c2', name: 'Holiday', category_group_id: 'g1', is_assignable: true },
    ],
  } as never)
  vi.mocked(categoriesApi.useCategoryGroups).mockReturnValue({
    data: [{ id: 'g1', name: 'Everyday' }],
  } as never)
})

describe('SettleWishDialog', () => {
  it('states the served figure, never a recomputed one', () => {
    renderDialog(wish(held()))
    expect(screen.getByText(/still holds/)).toBeInTheDocument()
    expect(screen.getByText('$400.00')).toBeInTheDocument()
  })

  it('sends the money to Ready to Assign by default and archives the envelope', async () => {
    renderDialog(wish(held()))
    fireEvent.click(screen.getByRole('button', { name: 'Move and archive' }))
    expect(settle).toHaveBeenCalledWith({
      id: 'w1',
      destination_category_id: null,
      keep_envelope: false,
    })
  })

  it('keeping the envelope still moves the money out', () => {
    renderDialog(wish(held()))
    fireEvent.click(screen.getByRole('button', { name: 'Keep the envelope' }))
    expect(settle).toHaveBeenCalledWith({
      id: 'w1',
      destination_category_id: null,
      keep_envelope: true,
    })
  })

  it('an overspent envelope asks to cover it, not to move money out of it', () => {
    renderDialog(wish(held({ available: -60 })))
    expect(screen.getByText(/overspent/)).toBeInTheDocument()
    expect(screen.getByLabelText('Cover from')).toBeInTheDocument()
    expect(screen.queryByLabelText('Move to')).not.toBeInTheDocument()
  })

  it('an empty envelope asks only whether to archive it', () => {
    renderDialog(wish(held({ available: 0 })))
    expect(screen.getByRole('button', { name: 'Archive it' })).toBeInTheDocument()
    // Nothing to move, so no destination to pick.
    expect(screen.queryByLabelText('Move to')).not.toBeInTheDocument()
    expect(screen.getByText(/still asking for the wish/)).toBeInTheDocument()
  })

  // The envelope being settled is filtered out of its own destination list,
  // but opening the combobox needs layout jsdom does not have. The guarantee
  // that matters is the server's refusal, pinned in
  // tests/integration/test_wishlist_settle.py.

  it('a bought wish reads as bought, not dropped', () => {
    renderDialog(wish(held(), 'done'))
    expect(screen.getByText(/is bought/)).toBeInTheDocument()
  })

  it('shows the server’s refusal inline rather than losing it to a toast', async () => {
    settle.mockRejectedValue({
      response: { data: { detail: 'Bike belongs to a card or a tracked debt' } },
    })
    renderDialog(wish(held()))
    fireEvent.click(screen.getByRole('button', { name: 'Move and archive' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/card or a tracked debt/)
  })
})
