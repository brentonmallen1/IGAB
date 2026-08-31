import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WishlistPanel } from './WishlistPanel'
import { useAppStore } from '../../../stores/appStore'
import { useGuideStore } from '../../../stores/guideStore'
import { useGuideOverview } from '../../../api/guide'
import * as wishlistApi from '../../../api/wishlist'
import type { Wish, Wishlist } from '../../../api/wishlist'

vi.mock('../../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/guide')>()),
  useGuideOverview: vi.fn(),
}))
vi.mock('../../../api/wishlist', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/wishlist')>()
  const mutation = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false })
  return {
    ...actual,
    useWishlist: vi.fn(),
    useUpdateWish: vi.fn(mutation),
    useDeleteWish: vi.fn(mutation),
    useReorderWishes: vi.fn(mutation),
    useDeleteProject: vi.fn(mutation),
    useSetWishlistSettings: vi.fn(mutation),
  }
})

function wish(over: Partial<Wish>): Wish {
  return {
    id: over.name ?? 'w',
    project_id: null,
    name: 'Bike',
    url: null,
    notes: null,
    cost: '1800',
    priority: 0,
    status: 'open',
    funding: {
      mode: 'own',
      category_id: 'c',
      category_name: 'Bike',
      inherited: false,
      owns_envelope: true,
      target_date: null,
    },
    cooling_until: null,
    cooling: false,
    last_affirmed_at: null,
    review_due: false,
    done_at: null,
    created_at: '2026-08-01T00:00:00Z',
    reach: { state: 'months', months: 8, date: '2027-04-26', ahead_cost: '0', progress: '0.30' },
    ...over,
  }
}

function payload(over: Partial<Wishlist>): Wishlist {
  return {
    enabled: true,
    items: [],
    history: [],
    projects: [],
    still_wanted: { count: 2, of: 5, months: 3 },
    review_due_count: 0,
    settings: { cooling_days: 30, review_after_days: 90 },
    drains: { month: '2026-08-01', total: '0', moves: [] },
    ...over,
  }
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <WishlistPanel />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  useGuideStore.setState({ wishlistView: 'flat', wishlistSort: 'reach' })
  vi.mocked(useGuideOverview).mockReturnValue({
    data: {
      concepts: [],
      thresholds: {},
      preferences: { personalization: true, checkup: true, wishlist: true },
      progress: {},
    },
  } as never)
})

describe('WishlistPanel', () => {
  it('shows the served counts, not recomputed ones', () => {
    vi.mocked(wishlistApi.useWishlist).mockReturnValue({
      data: payload({ items: [wish({})] }),
      isLoading: false,
    } as never)
    renderPanel()
    expect(screen.getByText('Added over 3 months ago and still wanted: 2 of 5')).toBeInTheDocument()
  })

  it('a cooling wish says so and its Done button is quiet', () => {
    vi.mocked(wishlistApi.useWishlist).mockReturnValue({
      data: payload({ items: [wish({ cooling: true, cooling_until: '2026-09-25' })] }),
      isLoading: false,
    } as never)
    renderPanel()
    expect(screen.getByText(/cooling off until/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Done' })).toHaveClass('wish__done--quiet')
  })

  it('the hero holds exactly three, by priority', () => {
    const items = [0, 1, 2, 3, 4].map((p) => wish({ name: `W${p}`, priority: p }))
    vi.mocked(wishlistApi.useWishlist).mockReturnValue({
      data: payload({ items }),
      isLoading: false,
    } as never)
    const { container } = renderPanel()
    const hero = container.querySelector('.guide-wishlist__hero')!
    expect(within(hero as HTMLElement).getAllByRole('article')).toHaveLength(3)
    expect(container.querySelectorAll('.wish')).toHaveLength(5)
  })

  it('history is collapsed by default', () => {
    vi.mocked(wishlistApi.useWishlist).mockReturnValue({
      data: payload({
        items: [wish({})],
        history: [wish({ name: 'Old', status: 'done', reach: null })],
      }),
      isLoading: false,
    } as never)
    renderPanel()
    expect(screen.queryByText(/dropped|done/)).not.toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
  })

  it('renders the drains it is served, with the distance', () => {
    vi.mocked(wishlistApi.useWishlist).mockReturnValue({
      data: payload({
        items: [wish({})],
        drains: {
          month: '2026-08-01',
          total: '60',
          moves: [
            {
              move_id: 'm1',
              month: '2026-08-01',
              date: '2026-08-12T09:30:00Z',
              amount: '60',
              from_category_id: 'c',
              from_name: 'Bike',
              to_category_id: 'd',
              to_name: 'Dining Out',
              affected: [{ item_id: 'w', name: 'Bike', months_further: '0.6' }],
            },
          ],
        },
      }),
      isLoading: false,
    } as never)
    renderPanel()
    expect(screen.getByText('Bike → Dining Out')).toBeInTheDocument()
    expect(screen.getByText(/about 3 weeks further away/)).toBeInTheDocument()
  })

  it('offers the review only when something is due', () => {
    vi.mocked(wishlistApi.useWishlist).mockReturnValue({
      data: payload({ items: [wish({ review_due: true })], review_due_count: 1 }),
      isLoading: false,
    } as never)
    renderPanel()
    expect(screen.getByRole('button', { name: 'Review' })).toBeInTheDocument()
  })

  it('reads as switched off when the preference is off', () => {
    vi.mocked(useGuideOverview).mockReturnValue({
      data: {
        concepts: [],
        thresholds: {},
        preferences: { personalization: true, checkup: true, wishlist: false },
        progress: {},
      },
    } as never)
    vi.mocked(wishlistApi.useWishlist).mockReturnValue({
      data: undefined,
      isLoading: false,
    } as never)
    renderPanel()
    expect(screen.getByText(/switched off/)).toBeInTheDocument()
  })
})
