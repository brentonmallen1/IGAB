/**
 * The wiring behind the Wishlist switch.
 *
 * `wishlistToggle.ts` decides what to send and is tested on its own. This is
 * the other half of that split: that the switch is actually connected to it,
 * with the real preview fetch and the real confirmation dialog passed in. A
 * pure function tested in isolation and never called is a function that works
 * perfectly and does nothing.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SettingsPage } from './SettingsPage'
import { useAppStore } from '../../stores/appStore'
import { fetchWishlistRetirePreview, useGuideOverview, useSetGuidePreferences } from '../../api/guide'
import { confirmAsync } from '../../stores/confirmStore'

vi.mock('../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/guide')>()),
  useGuideOverview: vi.fn(),
  useSetGuidePreferences: vi.fn(),
  fetchWishlistRetirePreview: vi.fn(),
}))

vi.mock('../../stores/confirmStore', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../stores/confirmStore')>()),
  confirmAsync: vi.fn(),
}))

const mutate = vi.fn()

const HOLDS_MONEY = { envelopes: ['New Bike'], available: '400.0000', is_empty: false }
const EMPTY = { envelopes: [], available: '0.0000', is_empty: true }

beforeEach(() => {
  vi.clearAllMocks()
  useAppStore.setState({ currentBudgetId: 'b1' })
  vi.mocked(useGuideOverview).mockReturnValue({
    data: {
      concepts: [],
      thresholds: {},
      preferences: { personalization: true, checkup: true, wishlist: true },
      progress: {},
    },
  } as never)
  vi.mocked(useSetGuidePreferences).mockReturnValue({ mutate, isPending: false } as never)
  vi.mocked(confirmAsync).mockResolvedValue(true)
})

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/settings']}>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function wishlistSwitch() {
  // The row is found by its label rather than by position, so reordering the
  // settings list does not silently point this at the Checkup toggle.
  const label = screen.getByText('Wishlist')
  const row = label.closest('.settings-row') as HTMLElement
  return row.querySelector('input[type="checkbox"]') as HTMLInputElement
}

describe('the Wishlist switch', () => {
  it('asks the server what turning it off would move', async () => {
    vi.mocked(fetchWishlistRetirePreview).mockResolvedValue(EMPTY)
    renderPage()
    await userEvent.click(wishlistSwitch())
    await waitFor(() => expect(fetchWishlistRetirePreview).toHaveBeenCalledWith('b1'))
  })

  it('confirms with the real dialog before letting money move', async () => {
    vi.mocked(fetchWishlistRetirePreview).mockResolvedValue(HOLDS_MONEY)
    renderPage()
    await userEvent.click(wishlistSwitch())

    await waitFor(() => expect(confirmAsync).toHaveBeenCalled())
    // The served figure reaches the dialog through the page's own formatter.
    const asked = vi.mocked(confirmAsync).mock.calls[0][0]
    expect(asked.message).toContain('New Bike')
    expect(asked.message).toMatch(/400/)

    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith({ wishlist: false, release_wishlist_money: true })
    )
  })

  it('sends nothing when the dialog is declined', async () => {
    vi.mocked(fetchWishlistRetirePreview).mockResolvedValue(HOLDS_MONEY)
    vi.mocked(confirmAsync).mockResolvedValue(false)
    renderPage()
    await userEvent.click(wishlistSwitch())

    await waitFor(() => expect(confirmAsync).toHaveBeenCalled())
    expect(mutate).not.toHaveBeenCalled()
  })

  it('turns off an empty wishlist without asking', async () => {
    vi.mocked(fetchWishlistRetirePreview).mockResolvedValue(EMPTY)
    renderPage()
    await userEvent.click(wishlistSwitch())

    await waitFor(() => expect(mutate).toHaveBeenCalledWith({ wishlist: false }))
    expect(confirmAsync).not.toHaveBeenCalled()
  })

  it('turning it on neither previews nor asks', async () => {
    vi.mocked(useGuideOverview).mockReturnValue({
      data: {
        concepts: [],
        thresholds: {},
        preferences: { personalization: true, checkup: true, wishlist: false },
        progress: {},
      },
    } as never)
    renderPage()
    await userEvent.click(wishlistSwitch())

    await waitFor(() => expect(mutate).toHaveBeenCalledWith({ wishlist: true }))
    expect(fetchWishlistRetirePreview).not.toHaveBeenCalled()
    expect(confirmAsync).not.toHaveBeenCalled()
  })
})
