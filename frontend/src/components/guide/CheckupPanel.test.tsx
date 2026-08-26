import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CheckupPanel } from './CheckupPanel'
import { useAppStore } from '../../stores/appStore'
import {
  useGuideCheckup,
  useGuideOverview,
  useRunHealthReport,
  type Checkup,
  type CheckupFinding,
  type FindingKind,
  type GuidePreferences,
} from '../../api/guide'

vi.mock('../../api/guide', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/guide')>()),
  useGuideOverview: vi.fn(),
  useGuideCheckup: vi.fn(),
  useRunHealthReport: vi.fn(),
}))

function overview(preferences: GuidePreferences) {
  return { data: { concepts: [], thresholds: {}, preferences, progress: {} } }
}

function finding(kind: FindingKind, rank: number, concept_key: string | null = null): CheckupFinding {
  return { kind, rank, concept_key, title: `Finding ${kind}`, detail: '', value: null, target: null, names: [] }
}

function checkup(findings: CheckupFinding[]): Checkup {
  return {
    enabled: true,
    as_of: '2026-08-26',
    last_run: null,
    metrics: [
      {
        key: 'high_interest_debt',
        label: 'Debt at 10%+ APR',
        value: '3410',
        target: '0',
        unit: 'money',
        detail: 'these debts are at 10% APR or higher',
        finding_kinds: ['high_interest_debt', 'unknown_rates'],
        report: 'liabilities',
      },
      {
        key: 'chronic_overspend',
        label: 'Overspent month after month',
        value: '0',
        target: '0',
        unit: 'count',
        detail: '',
        finding_kinds: ['chronic_overspend'],
        report: 'plan-reality',
      },
    ],
    findings,
  }
}

const SEVEN: CheckupFinding[] = [
  finding('high_interest_debt', 1),
  finding('ef_below_starter', 2, 'emergency_fund'),
  finding('chronic_overspend', 3),
  finding('moderate_debt', 5),
  finding('retirement_below_target', 6, 'retirement_contributions'),
  finding('stale_external', 7, 'hsa'),
  finding('unknown_rates', 8),
]

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CheckupPanel />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const ON: GuidePreferences = { personalization: true, checkup: true }

beforeEach(() => {
  useAppStore.setState({ currentBudgetId: 'b1' })
  vi.mocked(useGuideOverview).mockReturnValue(overview(ON) as never)
  vi.mocked(useRunHealthReport).mockReturnValue({
    // The run resolves straight away with the same payload the GET holds.
    mutate: (_: unknown, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.(),
    isPending: false,
    isError: false,
  } as never)
})

describe('CheckupPanel', () => {
  it('offers no report when reviews are off', () => {
    vi.mocked(useGuideOverview).mockReturnValue(
      overview({ personalization: true, checkup: false }) as never
    )
    vi.mocked(useGuideCheckup).mockReturnValue({ data: undefined, isLoading: false } as never)
    renderPanel()
    expect(screen.queryByRole('button', { name: /run health report/i })).not.toBeInTheDocument()
    expect(screen.getByText(/switched off/)).toBeInTheDocument()
  })

  it('shows five findings and counts the rest', async () => {
    vi.mocked(useGuideCheckup).mockReturnValue({ data: checkup(SEVEN), isLoading: false } as never)
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /run health report/i }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getAllByRole('listitem')).toHaveLength(5)
    expect(within(dialog).getByText(/and 2 more/)).toBeInTheDocument()
    expect(within(dialog).getByText(/7 things worth a look/)).toBeInTheDocument()
    // Close it: the dialog registers a history entry, and one left open would
    // leak into the next test's dialog.
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
  })

  it('a clean run says so rather than showing nothing', async () => {
    vi.mocked(useGuideCheckup).mockReturnValue({ data: checkup([]), isLoading: false } as never)
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /run health report/i }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/Nothing stood out/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
  })

  it('marks the metric a finding belongs to, and only that one', () => {
    vi.mocked(useGuideCheckup).mockReturnValue({
      data: checkup([finding('high_interest_debt', 1)]),
      isLoading: false,
    } as never)
    const { container } = renderPanel()
    const warned = container.querySelectorAll('.metric-card--warning')
    expect(warned).toHaveLength(1)
    expect(warned[0].textContent).toContain('Debt at 10%+ APR')
  })

  it('reads "Never run" until the report has been run', () => {
    vi.mocked(useGuideCheckup).mockReturnValue({ data: checkup([]), isLoading: false } as never)
    renderPanel()
    expect(screen.getByText('Never run')).toBeInTheDocument()
  })
})
