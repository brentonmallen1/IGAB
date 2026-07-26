import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import type {
  AccountCompositionReport,
  BudgetActualReport,
  BurnRateReport,
  CashFlowReport,
  DashboardMetrics,
  DayPatternsReport,
  LiabilitiesReport,
  IncomeExpenseReport,
  NetWorthReport,
  PayeeAnalysisReport,
  SeasonalityReport,
  SpendingGroupedReport,
  SpendingReport,
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

export function useSpendingReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  categoryIds?: string[],
  accountIds?: string[],
) {
  const catParam = categoryIds?.length ? categoryIds.join(',') : undefined
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'spending', budgetId, startDate, endDate, catParam, acctParam],
    queryFn: async () => {
      const { data } = await apiClient.get<SpendingReport>(`/${budgetId}/reports/spending`, {
        params: params({ start_date: startDate, end_date: endDate, category_ids: catParam, account_ids: acctParam }),
      })
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

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

export function useSpendingGroupedReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
  categoryIds?: string[],
  accountIds?: string[],
) {
  const catParam = categoryIds?.length ? categoryIds.join(',') : undefined
  const acctParam = accountIds?.length ? accountIds.join(',') : undefined
  return useQuery({
    queryKey: ['reports', 'spending-grouped', budgetId, startDate, endDate, catParam, acctParam],
    queryFn: async () => {
      const { data } = await apiClient.get<SpendingGroupedReport>(
        `/${budgetId}/reports/spending-grouped`,
        { params: params({ start_date: startDate, end_date: endDate, category_ids: catParam, account_ids: acctParam }) },
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: STALE,
  })
}

// ─── Seasonality ───────────────────────────────────────────────────────────

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
