import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { GuidePage } from './GuidePage'
import { useAppStore } from '../../stores/appStore'
import { useGuideStore } from '../../stores/guideStore'
import { useGuideOverview, type GuidePreferences } from '../../api/guide'

vi.mock('../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/guide')>()),
  useGuideOverview: vi.fn(),
}))

function prefs(preferences: Omit<GuidePreferences, 'wishlist'> & { wishlist?: boolean }) {
  preferences = { wishlist: true, ...preferences }
  vi.mocked(useGuideOverview).mockReturnValue({
    data: { concepts: [], thresholds: {}, preferences, progress: {} },
  } as never)
}

function renderPage(path = '/guide') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <GuidePage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  useGuideStore.setState({ activeTab: 'roadmap', activeTool: null })
})

describe('GuidePage', () => {
  it('offers the Checkup tab while reviews are on', () => {
    prefs({ personalization: true, checkup: true })
    renderPage()
    expect(screen.getByRole('button', { name: 'Checkup' })).toBeInTheDocument()
  })

  it('hides the Checkup tab when reviews are off', () => {
    prefs({ personalization: true, checkup: false })
    renderPage()
    expect(screen.queryByRole('button', { name: 'Checkup' })).not.toBeInTheDocument()
  })

  it('a roadmap link opens the Tools tab on the named calculator', () => {
    prefs({ personalization: true, checkup: true })
    renderPage('/guide?tab=tools&tool=payoff-plan')
    expect(useGuideStore.getState().activeTab).toBe('tools')
    expect(useGuideStore.getState().activeTool).toBe('payoff-plan')
    expect(screen.getByRole('heading', { name: 'Scenario tools' })).toBeInTheDocument()
  })

  it('ignores a tool it does not know', () => {
    prefs({ personalization: true, checkup: true })
    renderPage('/guide?tab=tools&tool=crystal-ball')
    expect(useGuideStore.getState().activeTab).toBe('tools')
    expect(useGuideStore.getState().activeTool).toBeNull()
  })

  it('hides the Wishlist tab when the wishlist is off', () => {
    prefs({ personalization: true, checkup: true, wishlist: false })
    renderPage()
    expect(screen.queryByRole('button', { name: 'Wishlist' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Checkup' })).toBeInTheDocument()
  })

  it('falls back to the roadmap when the persisted tab is switched off', () => {
    prefs({ personalization: false, checkup: false })
    useGuideStore.setState({ activeTab: 'checkup' })
    renderPage()
    expect(useGuideStore.getState().activeTab).toBe('roadmap')
  })
})
