import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useAppStore } from '../stores/appStore'
import { useBudgets } from '../api/budgets'
import type { NumberFormat, DateFormat, TimeFormat } from '../types'

export interface FormatSettings {
  currencyCode: string
  numberFormat: NumberFormat
  dateFormat: DateFormat
  timeFormat: TimeFormat
}

const DEFAULT_SETTINGS: FormatSettings = {
  currencyCode: 'USD',
  numberFormat: 'comma_dot',
  dateFormat: 'mdy',
  timeFormat: '12h',
}

const FormatContext = createContext<FormatSettings>(DEFAULT_SETTINGS)

export function FormatProvider({ children }: { children: ReactNode }) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: budgets } = useBudgets()

  const settings = useMemo<FormatSettings>(() => {
    const budget = budgets?.find((b) => b.id === budgetId)
    if (!budget) return DEFAULT_SETTINGS
    return {
      currencyCode: budget.currency_code,
      numberFormat: budget.number_format,
      dateFormat: budget.date_format,
      timeFormat: budget.time_format,
    }
  }, [budgets, budgetId])

  return <FormatContext.Provider value={settings}>{children}</FormatContext.Provider>
}

export function useFormatSettings(): FormatSettings {
  return useContext(FormatContext)
}
