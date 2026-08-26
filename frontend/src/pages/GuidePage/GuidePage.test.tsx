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

function prefs(preferences: GuidePreferences) {
  vi.mocked(useGuideOverview).mockReturnValue({
    data: { concepts: [], thresholds: {}, preferences, progress: {} },
  } as never)
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <GuidePage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  useGuideStore.setState({ activeTab: 'roadmap' })
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

  it('falls back to the roadmap when the persisted tab is switched off', () => {
    prefs({ personalization: false, checkup: false })
    useGuideStore.setState({ activeTab: 'checkup' })
    renderPage()
    expect(useGuideStore.getState().activeTab).toBe('roadmap')
  })
})
