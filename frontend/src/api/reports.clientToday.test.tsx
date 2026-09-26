/**
 * Every report asks for the reader's day.
 *
 * The server's clock is UTC: every evening west of it that is already
 * tomorrow, and on a month's last evening it is next month — Net Worth drew a
 * point for a month nobody had reached, and the averaging reports called the
 * running month complete. Two hooks sent `client_today`; the rest did not.
 *
 * This is the ratchet. Each report hook is listed with how to call it, and a
 * hook added to `reports.ts` without a row here fails the last test rather
 * than shipping a report that reads the server's day.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import * as reports from './reports'

vi.mock('./client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./client')>()),
  apiClient: { get: vi.fn(), put: vi.fn() },
}))

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

/** Each report hook, called the way a chart calls it. */
const HOOKS: Record<string, () => unknown> = {
  useIncomeExpenseReport: () => reports.useIncomeExpenseReport('b1'),
  useDashboardMetrics: () => reports.useDashboardMetrics('b1', '2026-08-01', '2026-08-31'),
  useReportRange: () => reports.useReportRange('b1'),
  useNetWorthReport: () => reports.useNetWorthReport('b1'),
  useAccountCompositionReport: () => reports.useAccountCompositionReport('b1'),
  useBurnRateReport: () => reports.useBurnRateReport('b1'),
  useCashFlowReport: () => reports.useCashFlowReport('b1'),
  useBudgetActualReport: () => reports.useBudgetActualReport('b1'),
  usePlanVsRealityReport: () => reports.usePlanVsRealityReport('b1'),
  useVarianceReport: () => reports.useVarianceReport('b1'),
  useVolatilityReport: () => reports.useVolatilityReport('b1'),
  useSavingsRateReport: () => reports.useSavingsRateReport('b1'),
  useSavingsContributors: () => reports.useSavingsContributors('b1', '2026-08-01', '2026-08-31'),
  useSpendingGroupedReport: () => reports.useSpendingGroupedReport('b1'),
  useEmergencyCoverageReport: () => reports.useEmergencyCoverageReport('b1'),
  useEssentialsReport: () => reports.useEssentialsReport('b1'),
  useSeasonalityReport: () => reports.useSeasonalityReport('b1'),
  usePayeeAnalysisReport: () => reports.usePayeeAnalysisReport('b1'),
  useDayPatternsReport: () => reports.useDayPatternsReport('b1'),
  useTimelineReport: () => reports.useTimelineReport('b1'),
  useLiabilitiesReport: () => reports.useLiabilitiesReport('b1'),
  useSubscriptionsReport: () => reports.useSubscriptionsReport('b1'),
  useSavingsReport: () => reports.useSavingsReport('b1'),
  useAnomaliesReport: () => reports.useAnomaliesReport('b1'),
  usePaydayEffectReport: () => reports.usePaydayEffectReport('b1'),
  useSpendingTrendsReport: () => reports.useSpendingTrendsReport('b1'),
  useIncomeBySourceReport: () => reports.useIncomeBySourceReport('b1'),
  useCategoryHistoryReport: () => reports.useCategoryHistoryReport('b1', 'c1'),
  useCostOfLivingReport: () => reports.useCostOfLivingReport('b1'),
  useDiscretionaryReport: () => reports.useDiscretionaryReport('b1'),
  useWishlistDisciplineReport: () => reports.useWishlistDisciplineReport('b1'),
}

/** Hooks that are not a report read for a day. Cash Projection is the one
 *  report not yet on `fetchReport`; it moves when its own rework lands. */
const NOT_A_DATED_REPORT = new Set([
  'useReportSettings',
  'useSetReportSettings',
  'useCashProjectionReport',
])

beforeEach(() => {
  // Only the clock: React Query's own timers must keep running.
  vi.useFakeTimers({ toFake: ['Date'] })
  // 9pm on the month's last evening, local — the server's UTC is next month.
  vi.setSystemTime(new Date(2026, 7, 31, 21, 0))
  vi.mocked(apiClient.get).mockReset()
  vi.mocked(apiClient.get).mockResolvedValue({ data: {} } as never)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('every report hook sends the reader’s day', () => {
  it.each(Object.keys(HOOKS))('%s', async (name) => {
    renderHook(HOOKS[name], { wrapper })
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled())
    const [url, config] = vi.mocked(apiClient.get).mock.calls[0]
    expect(url).toMatch(/^\/b1\/reports\//)
    expect(config).toMatchObject({ params: { client_today: '2026-08-31' } })
  })

  it('keeps what the chart asked for beside it', async () => {
    renderHook(() => reports.useVolatilityReport('b1', 6, true), { wrapper })
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled())
    expect(apiClient.get).toHaveBeenCalledWith('/b1/reports/volatility', {
      params: { months: 6, amortize: true, client_today: '2026-08-31' },
    })
  })

  it('drops a filter that was not set rather than sending it empty', async () => {
    renderHook(() => reports.useCashFlowReport('b1', undefined, undefined, 'spent', []), {
      wrapper,
    })
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled())
    expect(vi.mocked(apiClient.get).mock.calls[0][1]).toEqual({
      params: { mode: 'spent', client_today: '2026-08-31' },
    })
  })

  it('lists every hook reports.ts exports, so a new report cannot skip the day', () => {
    const exported = Object.keys(reports).filter((k) => /^use[A-Z]/.test(k))
    const unlisted = exported.filter((k) => !(k in HOOKS) && !NOT_A_DATED_REPORT.has(k))
    expect(unlisted).toEqual([])
  })
})
