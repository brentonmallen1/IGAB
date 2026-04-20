import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import type { IncomeExpenseReport, SpendingReport } from '../types'

export function useSpendingReport(
  budgetId: string | null,
  startDate?: string,
  endDate?: string,
) {
  return useQuery({
    queryKey: ['reports', 'spending', budgetId, startDate, endDate],
    queryFn: async () => {
      const { data } = await apiClient.get<SpendingReport>(`/${budgetId}/reports/spending`, {
        params: { start_date: startDate, end_date: endDate },
      })
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
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
    staleTime: 60_000,
  })
}

export function buildExportUrl(
  budgetId: string,
  format: 'csv' | 'json',
  startDate?: string,
  endDate?: string,
): string {
  const base = apiClient.defaults.baseURL ?? ''
  const params = new URLSearchParams({ format })
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)
  return `${base}/${budgetId}/reports/export?${params}`
}
