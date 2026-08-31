import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PositionStrip } from './PositionStrip'
import { ROADMAP, type SignalKey } from '../../content/roadmap'
import { useAppStore } from '../../stores/appStore'
import { useGuideStore } from '../../stores/guideStore'
import {
  useGuideCheckup,
  useGuideOverview,
  useGuideSignals,
  type CheckupFinding,
  type FindingKind,
  type Signal,
} from '../../api/guide'

vi.mock('../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/guide')>()),
  useGuideOverview: vi.fn(),
  useGuideSignals: vi.fn(),
  useGuideCheckup: vi.fn(),
}))

function signal(key: SignalKey, over: Partial<Signal> = {}): Signal {
  return {
    key,
    tracked: true,
    source: 'auto',
    met: null,
    value: null,
    detected_value: null,
    external_value: null,
    external_declared: false,
    external_as_of: null,
    target: null,
    starter_target: null,
    starter_met: null,
    reason: '',
    entities: {},
    gaps: [],
    note: null,
    ...over,
  }
}

function finding(kind: FindingKind, concept_key: string, title: string): CheckupFinding {
  return { kind, rank: 1, concept_key, title, detail: '', value: null, target: null, names: [] }
}

function arrange({
  progress = {},
  signals = [],
  findings = [],
}: {
  progress?: Record<string, 'done' | 'skipped'>
  signals?: Signal[]
  findings?: CheckupFinding[]
}) {
  const preferences = { personalization: true, checkup: true, wishlist: true }
  vi.mocked(useGuideOverview).mockReturnValue({
    data: { concepts: [], thresholds: {}, preferences, progress },
  } as never)
  vi.mocked(useGuideSignals).mockReturnValue({
    data: { personalization: true, concepts: signals },
    isLoading: false,
  } as never)
  vi.mocked(useGuideCheckup).mockReturnValue({
    data: { enabled: true, as_of: '2026-08-26', last_run: null, metrics: [], findings },
  } as never)
}

const EMPTY_FUND = {
  signals: [
    signal('budget_exists', { met: true }),
    signal('essential_expenses', { met: true }),
    signal('emergency_fund', { met: false, starter_met: false }),
  ],
  findings: [finding('ef_not_started', 'emergency_fund', 'No emergency fund yet')],
}

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  useGuideStore.setState({ roadmapView: 'journey', expandedStages: [] })
})

describe('PositionStrip', () => {
  it('draws one dot per stage and names the current one in the finding’s words', () => {
    arrange(EMPTY_FUND)
    render(<PositionStrip />)
    expect(screen.getAllByRole('listitem')).toHaveLength(ROADMAP.length)
    expect(
      screen.getByRole('button', { name: /You’re on Step 1 — Build a starter emergency fund/ })
    ).toBeInTheDocument()
    expect(screen.getByText(/No emergency fund yet/)).toBeInTheDocument()
    expect(
      screen.getByText(new RegExp(`1 of ${ROADMAP.length} stages behind you`))
    ).toBeInTheDocument()
    const foundation = ROADMAP[0]
    expect(
      screen.getByRole('button', {
        name: `Step ${foundation.step} — ${foundation.title}: looks done`,
      })
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { current: 'step' })).toHaveAccessibleName(/you are here/)
  })

  it('jumping from the Map lands in Journey with the stage open', async () => {
    arrange(EMPTY_FUND)
    useGuideStore.setState({ roadmapView: 'map', expandedStages: [] })
    render(<PositionStrip />)
    await userEvent.click(screen.getByRole('button', { name: /You’re on Step 1/ }))
    expect(useGuideStore.getState().roadmapView).toBe('journey')
    expect(useGuideStore.getState().expandedStages).toContain('starter-emergency-fund')
  })

  it('a marked stage shows the mark, and everything marked means nothing is current', () => {
    const progress = Object.fromEntries(ROADMAP.map((s) => [s.id, 'done' as const]))
    arrange({ progress })
    render(<PositionStrip />)
    expect(screen.getByText(/Nothing left the roadmap can see/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /you marked this done/ })).toHaveLength(
      ROADMAP.length
    )
  })
})
