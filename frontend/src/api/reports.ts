import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type {
  CostOfLivingReport,
  DiscretionaryReport,
  WishlistDisciplineReport,
  AccountCompositionReport,
  AnomalyReport,
  BudgetActualReport,
  BurnRateReport,
  CashFlowReport,
  CashProjectionReport,
  DashboardMetrics,
  DayPatternsReport,
  LiabilitiesReport,
  IncomeExpenseReport,
  NetWorthReport,
  PaydayEffectReport,
  PayeeAnalysisReport,
  PlanRealityReport,
  SavingsReport,
  SeasonalityReport,
  EmergencyCoverageReport,
  EssentialsReport,
  SpendingGroupedReport,
  SubscriptionsReport,
  TimelineReport,
  VarianceReport,
  VolatilityReport,
  SpendingTrendsReport,
  IncomeBySourceReport,
  CategoryHistoryReport,
  ReportSettings,
} from '../types'
import { ROOT } from './queryKeys'
import { today } from '../utils/dates'

const STALE = 60_000

type QueryValue = string | number | boolean | undefined | null

/** A report's query, minus what was not asked: an absent filter is no param. */
function params(obj: Record<string, QueryValue>) {
  const p: Record<string, string | number | boolean> = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v != null && v !== '') p[k] = v
  }
  return p
}

/**
 * GET one report, for the reader's day.
 *
 * The server cannot know what day it is for the person reading: its clock is
 * UTC, already tomorrow every evening west of it and next month on a month's
 * last evening — so a report that ends "today" or leaves the running month
 * out drew a month nobody had reached yet. `client_today` rides on every
 * report request (`api/v1/params.ReaderToday` reads it), read when the request
 * is made, so a tab left open past midnight asks for the new day on its next
 * fetch. Every report hook goes through here rather than naming the day
 * itself: two of them used to, and the other twenty-odd did not.
 * `reports.clientToday.test.tsx` holds each hook to it.
 */
async function fetchReport<T>(
  budgetId: string | null,
  report: string,
  query: Record<string, QueryValue> = {}
): Promise<T> {
  const { data } = await apiClient.get<T>(`/${budgetId}/reports/${report}`, {
    params: params({ ...query, client_today: today() }),
  })
  return data
}

/**
 * Which categories a report is about, as the filter bar set it.
 *
 * One object rather than three arguments threaded through every hook. The
 * three axes are one question — they UNION on the server
 * (`services/report_scope.py`) — and a chart that happened to pass two of the
 * three would quietly widen its own report with nothing on screen to say so.
 * Passing them together also means a chart cannot forget the one that was
 * added last.
 */
export interface ReportScope {
  categoryIds?: string[]
  tagIds?: string[]
  /** A saved filter's effective set, resolved server-side. */
  filterId?: string | null
}

/** The scope as query params. Also the cache key — `useQuery` keys on this
 *  object, so a scope change refetches and two scopes never share a cache
 *  entry. */
export function scopeParams(scope: ReportScope | undefined) {
  return {
    category_ids: scope?.categoryIds?.length ? scope.categoryIds.join(',') : undefined,
    tag_ids: scope?.tagIds?.length ? scope.tagIds.join(',') : undefined,
    filter_id: scope?.filterId ?? undefined,
  }
}

// ─── Existing ──────────────────────────────────────────────────────────────

// `useSpendingReport` lived here, unused: /reports/spending is served but no
// component asks for it — spending-grouped supersedes it. It was the third
// site missing the class-excluded note, and a note nothing renders is not a
// fix. Removed rather than patched; the endpoint stays for API consumers.

export function useIncomeExpenseReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'income-expense', budgetId, months],
    queryFn: () => fetchReport<IncomeExpenseReport>(budgetId, 'income-expense', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

/** The API path for a transaction export — fed to `downloadAuthed`, never to
 *  an `<a href>`: the endpoint requires a bearer token that only the axios
 *  interceptor attaches, so a plain link 401s. */
export function exportTransactionsPath(
  budgetId: string,
  format: 'csv' | 'json',
  startDate?: string,
  endDate?: string
): string {
  const p = new URLSearchParams({ format })
  if (startDate) p.set('start_date', startDate)
  if (endDate) p.set('end_date', endDate)
  return `/${budgetId}/reports/export?${p}`
}

// ─── Dashboard ─────────────────────────────────────────────────────────────

export function useDashboardMetrics(budgetId: string | null, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: [ROOT.reports, 'dashboard', budgetId, startDate, endDate],
    queryFn: () =>
      fetchReport<DashboardMetrics>(budgetId, 'dashboard', {
        start_date: startDate,
        end_date: endDate,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Available range ───────────────────────────────────────────────────────

export interface ReportRange {
  /** First of the month the oldest transaction falls in; null for an empty budget. */
  earliest_month: string | null
  /** Calendar months from that month to this one, inclusive. 0 means no history. */
  months_available: number
}

/** How far back this budget's reports can look — what the range picker offers,
 *  and what its "All time" resolves to. */
export function useReportRange(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.reports, 'range', budgetId],
    queryFn: () => fetchReport<ReportRange>(budgetId, 'range'),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Net Worth ─────────────────────────────────────────────────────────────

export function useNetWorthReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'net-worth', budgetId, months],
    queryFn: () => fetchReport<NetWorthReport>(budgetId, 'net-worth', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Account Composition ───────────────────────────────────────────────────

export function useAccountCompositionReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'account-composition', budgetId, months],
    queryFn: () =>
      fetchReport<AccountCompositionReport>(budgetId, 'account-composition', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Burn Rate ─────────────────────────────────────────────────────────────

export function useBurnRateReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'burn-rate', budgetId, months],
    queryFn: () => fetchReport<BurnRateReport>(budgetId, 'burn-rate', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Cash Flow ─────────────────────────────────────────────────────────────

export function useCashFlowReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  mode: 'spent' | 'budgeted' = 'spent',
  accountIds?: string[],
  options?: { enabled?: boolean }
) {
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: [ROOT.reports, 'cash-flow', budgetId, startDate, endDate, mode, acctParam],
    queryFn: () =>
      fetchReport<CashFlowReport>(budgetId, 'cash-flow', {
        start_date: startDate,
        end_date: endDate,
        mode,
        account_ids: acctParam,
      }),
    enabled: !!budgetId && (options?.enabled ?? true),
    staleTime: STALE,
  })
}

// ─── Budget vs Actual ──────────────────────────────────────────────────────

export function useBudgetActualReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  scope?: ReportScope
) {
  // The whole scope, not the category ids alone: the filter bar offers tags
  // and saved filters on this tab too, and the report ignored both.
  const scopeQuery = scopeParams(scope)
  return useQuery({
    queryKey: [ROOT.reports, 'budget-actual', budgetId, startDate, endDate, scopeQuery],
    queryFn: () =>
      fetchReport<BudgetActualReport>(budgetId, 'budget-actual', {
        start_date: startDate,
        end_date: endDate,
        ...scopeQuery,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Plan vs Reality ───────────────────────────────────────────────────────

export function usePlanVsRealityReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'plan-vs-reality', budgetId, months],
    queryFn: () => fetchReport<PlanRealityReport>(budgetId, 'plan-vs-reality', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Variance ──────────────────────────────────────────────────────────────

export function useVarianceReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'variance', budgetId, months],
    queryFn: () => fetchReport<VarianceReport>(budgetId, 'variance', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Volatility ────────────────────────────────────────────────────────────

export function useVolatilityReport(budgetId: string | null, months = 12, amortize = false) {
  return useQuery({
    queryKey: [ROOT.reports, 'volatility', budgetId, months, amortize],
    queryFn: () => fetchReport<VolatilityReport>(budgetId, 'volatility', { months, amortize }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Spending Grouped ──────────────────────────────────────────────────────

export interface SavingsRateMonth {
  month: string
  income: number
  spending: number
  /** Saved: `savings_moved + savings_held` (backend `domain/savings.py`). */
  savings: number
  /** Money moved into savings — SAVINGS-class flows. */
  savings_moved: number
  /** What kept-here Savings envelopes came to hold. */
  savings_held: number
  debt_principal: number
  /** null when there was no income that month — a gap, not a zero. */
  savings_rate: number | null
  savings_rate_with_debt: number | null
}

export interface SavingsRateReport {
  months: SavingsRateMonth[]
  /** The dates `summary` covers — the first month's start through today.
   *  The savings-rate dialog asks for the contributors of exactly this. */
  start_date: string
  end_date: string
  summary: {
    income: number
    spending: number
    savings: number
    savings_moved: number
    savings_held: number
    debt_principal: number
    savings_rate: number | null
    savings_rate_with_debt: number | null
  }
}

export function useSavingsRateReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'savings-rate', budgetId, months],
    queryFn: () => fetchReport<SavingsRateReport>(budgetId, 'savings-rate', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

/** One place money counted toward savings (or debt principal) went, named by
 *  destination — `report_basics.savings_contributors` says how. `total` is
 *  negative for money drawn back into the budget. A kept-here Savings
 *  envelope's held change is a `category` row with its own served reason. */
export interface SavingsContributor {
  kind: 'account' | 'category'
  id: string
  name: string
  /** The ActivityReason value that decided these rows. */
  reason: string
  /** Served copy for that reason — never spell it here. */
  reason_label: string
  total: number
  count: number
}

export interface SavingsContributors {
  start_date: string
  end_date: string
  income: number
  /** Saved: `savings_moved + savings_held`. */
  savings: number
  savings_moved: number
  savings_held: number
  debt_principal: number
  /** Each list sums to its total exactly, and is ordered by magnitude. */
  savings_contributors: SavingsContributor[]
  debt_contributors: SavingsContributor[]
  income_sources: { payee_id: string | null; payee_name: string; total: number; count: number }[]
}

/** What a savings rate over a window was made of. Fetched only while the
 *  dialog that shows it is open — the dialog mounts this hook, the cards do
 *  not. */
export function useSavingsContributors(
  budgetId: string | null,
  startDate: string,
  endDate: string
) {
  return useQuery({
    queryKey: [ROOT.reports, 'savings-contributors', budgetId, startDate, endDate],
    queryFn: () =>
      fetchReport<SavingsContributors>(budgetId, 'savings-contributors', {
        start_date: startDate,
        end_date: endDate,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

export function useSpendingGroupedReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  scope?: ReportScope,
  accountIds?: string[],
  /** Spending reports mean money spent, so saving and debt principal are left
   *  out by default. Set to bring them back into the totals. */
  includeSavings?: boolean,
  /** Roll up by this view's groups instead of the budget's own. A view is an
   *  arrangement and the scope is a predicate; both can be on. */
  viewId?: string | null
) {
  const scopeQuery = scopeParams(scope)
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: [
      ROOT.reports,
      'spending-grouped',
      budgetId,
      startDate,
      endDate,
      scopeQuery,
      acctParam,
      includeSavings,
      viewId,
    ],
    queryFn: () =>
      fetchReport<SpendingGroupedReport>(budgetId, 'spending-grouped', {
        start_date: startDate,
        end_date: endDate,
        ...scopeQuery,
        account_ids: acctParam,
        include_savings: includeSavings ? 'true' : undefined,
        view_id: viewId ?? undefined,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Seasonality ───────────────────────────────────────────────────────────

export function useEmergencyCoverageReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'emergency-fund', budgetId, months],
    queryFn: () => fetchReport<EmergencyCoverageReport>(budgetId, 'emergency-fund', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

/** The budget's report settings — `services/report_settings.py`. */
export function useReportSettings(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.reportSettings, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<ReportSettings>(`/${budgetId}/reports/settings`)
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

/**
 * Everything that reads the essentials figure, which the spread setting moves:
 * the Overview card, the Essentials and Emergency Fund reports, the Guide's
 * signals (its emergency-fund target and starter), the checkup and the sizer.
 * One list, read by the setting's mutation and by undo, so flipping the
 * setting and undoing the flip stale the same surfaces.
 */
export function invalidateAfterReportSettings(qc: QueryClient, budgetId: string | null) {
  const keys = [
    [ROOT.reportSettings, budgetId],
    [ROOT.reports, 'dashboard', budgetId],
    [ROOT.reports, 'essentials', budgetId],
    [ROOT.reports, 'emergency-fund', budgetId],
    [ROOT.guideSignals, budgetId],
    [ROOT.guideCheckup, budgetId],
    [ROOT.guideScenario, 'emergency-fund', budgetId],
  ]
  return Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })))
}

export function useSetReportSettings(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (settings: ReportSettings) => {
      const { data } = await apiClient.put<ReportSettings>(
        `/${budgetId}/reports/settings`,
        settings
      )
      return data
    },
    onSuccess: (data) => {
      qc.setQueryData([ROOT.reportSettings, budgetId], data)
      return invalidateAfterReportSettings(qc, budgetId)
    },
  })
}

export function useEssentialsReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'essentials', budgetId, months],
    queryFn: () => fetchReport<EssentialsReport>(budgetId, 'essentials', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

export function useSeasonalityReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'seasonality', budgetId, months],
    queryFn: () => fetchReport<SeasonalityReport>(budgetId, 'seasonality', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Payee Analysis ────────────────────────────────────────────────────────

export function usePayeeAnalysisReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  limit = 25,
  payeeIds?: string[],
  accountIds?: string[]
) {
  const payeeParam = payeeIds?.length ? payeeIds.join(',') : undefined
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: [
      ROOT.reports,
      'payee-analysis',
      budgetId,
      startDate,
      endDate,
      limit,
      payeeParam,
      acctParam,
    ],
    queryFn: () =>
      fetchReport<PayeeAnalysisReport>(budgetId, 'payee-analysis', {
        start_date: startDate,
        end_date: endDate,
        limit,
        payee_ids: payeeParam,
        account_ids: acctParam,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Day Patterns ──────────────────────────────────────────────────────────

export function useDayPatternsReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  scope?: ReportScope,
  accountIds?: string[]
) {
  const scopeQuery = scopeParams(scope)
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: [ROOT.reports, 'day-patterns', budgetId, startDate, endDate, scopeQuery, acctParam],
    queryFn: () =>
      fetchReport<DayPatternsReport>(budgetId, 'day-patterns', {
        start_date: startDate,
        end_date: endDate,
        ...scopeQuery,
        account_ids: acctParam,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Timeline (Large Transactions) ─────────────────────────────────────────

export function useTimelineReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  limit = 50,
  scope?: ReportScope,
  accountIds?: string[]
) {
  const scopeQuery = scopeParams(scope)
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: [
      ROOT.reports,
      'timeline',
      budgetId,
      startDate,
      endDate,
      limit,
      scopeQuery,
      acctParam,
    ],
    queryFn: () =>
      fetchReport<TimelineReport>(budgetId, 'large-transactions', {
        start_date: startDate,
        end_date: endDate,
        limit,
        ...scopeQuery,
        account_ids: acctParam,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

export function useLiabilitiesReport(
  budgetId: string | null,
  liabilityType?: string,
  mode?: string
) {
  return useQuery({
    queryKey: [ROOT.reports, 'liabilities', budgetId, liabilityType ?? null, mode ?? null],
    queryFn: () =>
      fetchReport<LiabilitiesReport>(budgetId, 'liabilities', {
        liability_type: liabilityType,
        mode,
      }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Subscriptions ─────────────────────────────────────────────────────────

export function useSubscriptionsReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'subscriptions', budgetId, months],
    queryFn: () => fetchReport<SubscriptionsReport>(budgetId, 'subscriptions', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Savings ───────────────────────────────────────────────────────────────

export function useSavingsReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'savings', budgetId, months],
    queryFn: () => fetchReport<SavingsReport>(budgetId, 'savings', { months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Anomalies ─────────────────────────────────────────────────────────────

export function useAnomaliesReport(budgetId: string | null, months = 12, threshold = 2.0) {
  return useQuery({
    queryKey: [ROOT.reports, 'anomalies', budgetId, months, threshold],
    queryFn: () => fetchReport<AnomalyReport>(budgetId, 'anomalies', { months, threshold }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Payday Effect ────────────────────────────────────────────────────────────

export function usePaydayEffectReport(budgetId: string | null, window = 14, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'payday-effect', budgetId, window, months],
    queryFn: () => fetchReport<PaydayEffectReport>(budgetId, 'payday-effect', { window, months }),
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Cash Projection ──────────────────────────────────────────────────────────

/** Starts on the reader's today: the server's is UTC, and of an evening it is
 *  already tomorrow there. */
export function useCashProjectionReport(budgetId: string | null, days = 90) {
  return useQuery({
    queryKey: [ROOT.reports, 'cash-projection', budgetId, days],
    queryFn: async () => {
      const { data } = await apiClient.get<CashProjectionReport>(
        `/${budgetId}/reports/cash-projection`,
        { params: { days, client_today: today() } }
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Spending trends / income by source / category history ────────────────

export function useSpendingTrendsReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  scope?: ReportScope,
  accountIds?: string[],
  includeSavings?: boolean
) {
  const scopeQuery = scopeParams(scope)
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: [
      ROOT.reports,
      'spending-trends',
      budgetId,
      startDate,
      endDate,
      scopeQuery,
      acctParam,
      includeSavings,
    ],
    queryFn: () =>
      fetchReport<SpendingTrendsReport>(budgetId, 'spending-trends', {
        start_date: startDate,
        end_date: endDate,
        ...scopeQuery,
        account_ids: acctParam,
        include_savings: includeSavings ? 'true' : undefined,
      }),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useIncomeBySourceReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'income-by-source', budgetId, months],
    queryFn: () => fetchReport<IncomeBySourceReport>(budgetId, 'income-by-source', { months }),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCategoryHistoryReport(
  budgetId: string | null,
  categoryId: string | null,
  months = 12
) {
  return useQuery({
    queryKey: [ROOT.reports, 'category-history', budgetId, categoryId, months],
    queryFn: () =>
      fetchReport<CategoryHistoryReport>(budgetId, 'category-history', {
        category_id: categoryId,
        months,
      }),
    enabled: !!budgetId && !!categoryId,
    staleTime: 60_000,
  })
}

export function useCostOfLivingReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'cost-of-living', budgetId, months],
    queryFn: () => fetchReport<CostOfLivingReport>(budgetId, 'cost-of-living', { months }),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useDiscretionaryReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: [ROOT.reports, 'discretionary', budgetId, months],
    queryFn: () => fetchReport<DiscretionaryReport>(budgetId, 'discretionary', { months }),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

/** No months parameter: the wishlist report is all-time on purpose, because a
 *  habit measured over twelve months forgets what you resisted two years ago. */
export function useWishlistDisciplineReport(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.reports, 'wishlist', budgetId],
    queryFn: () => fetchReport<WishlistDisciplineReport>(budgetId, 'wishlist'),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}
