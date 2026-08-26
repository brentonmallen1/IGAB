import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import type {
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
  EssentialsReport,
  SpendingGroupedReport,
  SubscriptionsReport,
  TimelineReport,
  VarianceReport,
  VolatilityReport,
} from '../types'

const STALE = 60_000

function params(obj: Record<string, string | number | undefined | null>) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(obj)) {
    if (v != null && v !== '') p.set(k, String(v))
  }
  return p
}

// ─── Existing ──────────────────────────────────────────────────────────────

// `useSpendingReport` lived here, unused: /reports/spending is served but no
// component asks for it — spending-grouped supersedes it. It was the third
// site missing the class-excluded note, and a note nothing renders is not a
// fix. Removed rather than patched; the endpoint stays for API consumers.

export function useIncomeExpenseReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'income-expense', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<IncomeExpenseReport>(
        `/${budgetId}/reports/income-expense`,
        { params: { months } },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

export function buildExportUrl(
  budgetId: string,
  format: 'csv' | 'json',
  startDate?: string,
  endDate?: string,
): string {
  const base = apiClient.defaults.baseURL ?? ''
  const p = new URLSearchParams({ format })
  if (startDate) p.set('start_date', startDate)
  if (endDate) p.set('end_date', endDate)
  return `${base}/${budgetId}/reports/export?${p}`
}

// ─── Dashboard ─────────────────────────────────────────────────────────────

export function useDashboardMetrics(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
) {
  return useQuery({
    queryKey: ['reports', 'dashboard', budgetId, startDate, endDate],
    queryFn: async () => {
      const { data } = await apiClient.get<DashboardMetrics>(
        `/${budgetId}/reports/dashboard`,
        { params: params({ start_date: startDate, end_date: endDate }) },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Net Worth ─────────────────────────────────────────────────────────────

export function useNetWorthReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'net-worth', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<NetWorthReport>(
        `/${budgetId}/reports/net-worth`,
        { params: { months } },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Account Composition ───────────────────────────────────────────────────

export function useAccountCompositionReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'account-composition', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<AccountCompositionReport>(
        `/${budgetId}/reports/account-composition`,
        { params: { months } },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Burn Rate ─────────────────────────────────────────────────────────────

export function useBurnRateReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'burn-rate', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<BurnRateReport>(
        `/${budgetId}/reports/burn-rate`,
        { params: { months } },
      )
      return data
    },
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
  options?: { enabled?: boolean },
) {
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'cash-flow', budgetId, startDate, endDate, mode, acctParam],
    queryFn: async () => {
      const { data } = await apiClient.get<CashFlowReport>(
        `/${budgetId}/reports/cash-flow`,
        { params: params({ start_date: startDate, end_date: endDate, mode, account_ids: acctParam }) },
      )
      return data
    },
    enabled: !!budgetId && (options?.enabled ?? true),
    staleTime: STALE,
  })
}

// ─── Budget vs Actual ──────────────────────────────────────────────────────

export function useBudgetActualReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  categoryIds?: string[],
) {
  const catParam = categoryIds?.length ? categoryIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'budget-actual', budgetId, startDate, endDate, catParam],
    queryFn: async () => {
      const { data } = await apiClient.get<BudgetActualReport>(
        `/${budgetId}/reports/budget-actual`,
        { params: params({ start_date: startDate, end_date: endDate, category_ids: catParam }) },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Plan vs Reality ───────────────────────────────────────────────────────

export function usePlanVsRealityReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'plan-vs-reality', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<PlanRealityReport>(
        `/${budgetId}/reports/plan-vs-reality`,
        { params: { months } },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Variance ──────────────────────────────────────────────────────────────

export function useVarianceReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'variance', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<VarianceReport>(
        `/${budgetId}/reports/variance`,
        { params: { months } },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Volatility ────────────────────────────────────────────────────────────

export function useVolatilityReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'volatility', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<VolatilityReport>(
        `/${budgetId}/reports/volatility`,
        { params: { months } },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Spending Grouped ──────────────────────────────────────────────────────

export interface SavingsRateMonth {
  month: string
  income: string
  spending: string
  savings: string
  debt_principal: string
  /** null when there was no income that month — a gap, not a zero. */
  savings_rate: number | null
  savings_rate_with_debt: number | null
}

export interface SavingsRateReport {
  months: SavingsRateMonth[]
  summary: {
    income: string
    spending: string
    savings: string
    debt_principal: string
    savings_rate: number | null
    savings_rate_with_debt: number | null
  }
}

export function useSavingsRateReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'savings-rate', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<SavingsRateReport>(
        `/${budgetId}/reports/savings-rate`,
        { params: params({ months }) },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

export function useSpendingGroupedReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  categoryIds?: string[],
  accountIds?: string[],
  /** Spending reports mean money spent, so saving and debt principal are left
   *  out by default. Set to bring them back into the totals. */
  includeSavings?: boolean,
  /** Roll up by this view's groups instead of the budget's own. */
  viewId?: string | null,
) {
  const catParam = categoryIds?.length ? categoryIds.join(',') : undefined
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'spending-grouped', budgetId, startDate, endDate, catParam, acctParam, includeSavings, viewId],
    queryFn: async () => {
      const { data } = await apiClient.get<SpendingGroupedReport>(
        `/${budgetId}/reports/spending-grouped`,
        {
          params: params({
            start_date: startDate,
            end_date: endDate,
            category_ids: catParam,
            account_ids: acctParam,
            include_savings: includeSavings ? 'true' : undefined,
            view_id: viewId ?? undefined,
          }),
        },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Seasonality ───────────────────────────────────────────────────────────

export function useEssentialsReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'essentials', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<EssentialsReport>(
        `/${budgetId}/reports/essentials`,
        { params: { months } },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

export function useSeasonalityReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'seasonality', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<SeasonalityReport>(
        `/${budgetId}/reports/seasonality`,
        { params: { months } },
      )
      return data
    },
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
  accountIds?: string[],
) {
  const payeeParam = payeeIds?.length ? payeeIds.join(',') : undefined
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'payee-analysis', budgetId, startDate, endDate, limit, payeeParam, acctParam],
    queryFn: async () => {
      const { data } = await apiClient.get<PayeeAnalysisReport>(
        `/${budgetId}/reports/payee-analysis`,
        { params: params({ start_date: startDate, end_date: endDate, limit, payee_ids: payeeParam, account_ids: acctParam }) },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Day Patterns ──────────────────────────────────────────────────────────

export function useDayPatternsReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  categoryIds?: string[],
  accountIds?: string[],
) {
  const catParam = categoryIds?.length ? categoryIds.join(',') : undefined
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'day-patterns', budgetId, startDate, endDate, catParam, acctParam],
    queryFn: async () => {
      const { data } = await apiClient.get<DayPatternsReport>(
        `/${budgetId}/reports/day-patterns`,
        { params: params({ start_date: startDate, end_date: endDate, category_ids: catParam, account_ids: acctParam }) },
      )
      return data
    },
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
  categoryIds?: string[],
  accountIds?: string[],
) {
  const catParam = categoryIds?.length ? categoryIds.join(',') : undefined
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'timeline', budgetId, startDate, endDate, limit, catParam, acctParam],
    queryFn: async () => {
      const { data } = await apiClient.get<TimelineReport>(
        `/${budgetId}/reports/large-transactions`,
        { params: params({ start_date: startDate, end_date: endDate, limit, category_ids: catParam, account_ids: acctParam }) },
      )
      return data
    },
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
    queryKey: ['reports', 'liabilities', budgetId, liabilityType ?? null, mode ?? null],
    queryFn: async () => {
      const { data } = await apiClient.get<LiabilitiesReport>(
        `/${budgetId}/reports/liabilities`,
        { params: params({ liability_type: liabilityType, mode }) }
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Subscriptions ─────────────────────────────────────────────────────────

export function useSubscriptionsReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'subscriptions', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<SubscriptionsReport>(
        `/${budgetId}/reports/subscriptions`,
        { params: { months } }
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Savings ───────────────────────────────────────────────────────────────

export function useSavingsReport(budgetId: string | null, months = 12) {
  return useQuery({
    queryKey: ['reports', 'savings', budgetId, months],
    queryFn: async () => {
      const { data } = await apiClient.get<SavingsReport>(
        `/${budgetId}/reports/savings`,
        { params: { months } }
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Anomalies ─────────────────────────────────────────────────────────────

export function useAnomaliesReport(
  budgetId: string | null,
  months = 12,
  threshold = 2.0
) {
  return useQuery({
    queryKey: ['reports', 'anomalies', budgetId, months, threshold],
    queryFn: async () => {
      const { data } = await apiClient.get<AnomalyReport>(
        `/${budgetId}/reports/anomalies`,
        { params: { months, threshold } }
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Payday Effect ────────────────────────────────────────────────────────────

export function usePaydayEffectReport(
  budgetId: string | null,
  window = 14,
  months = 12
) {
  return useQuery({
    queryKey: ['reports', 'payday-effect', budgetId, window, months],
    queryFn: async () => {
      const { data } = await apiClient.get<PaydayEffectReport>(
        `/${budgetId}/reports/payday-effect`,
        { params: { window, months } }
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Cash Projection ──────────────────────────────────────────────────────────

export function useCashProjectionReport(budgetId: string | null, days = 90) {
  return useQuery({
    queryKey: ['reports', 'cash-projection', budgetId, days],
    queryFn: async () => {
      const { data } = await apiClient.get<CashProjectionReport>(
        `/${budgetId}/reports/cash-projection`,
        { params: { days } }
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}
