import { useCallback } from 'react'
import { useFormatSettings } from '../contexts/FormatContext'
import { formatMoneyWithOptions, formatAmountWithOptions } from '../utils/money'
import { formatDateWithOptions, formatMonthWithOptions, formatTimeWithOptions } from '../utils/dates'

export function useFormatters() {
  const settings = useFormatSettings()

  const formatMoney = useCallback(
    (amount: number) => formatMoneyWithOptions(amount, settings.currencyCode, settings.numberFormat),
    [settings.currencyCode, settings.numberFormat]
  )

  const formatAmount = useCallback(
    (amount: number) => formatAmountWithOptions(amount, settings.numberFormat),
    [settings.numberFormat]
  )

  const formatDate = useCallback(
    (dateStr: string) => formatDateWithOptions(dateStr, settings.dateFormat),
    [settings.dateFormat]
  )

  const formatMonth = useCallback(
    (monthStr: string) => formatMonthWithOptions(monthStr, settings.dateFormat),
    [settings.dateFormat]
  )

  const formatTime = useCallback(
    (hour: number, minute: number) => formatTimeWithOptions(hour, minute, settings.timeFormat),
    [settings.timeFormat]
  )

  return { formatMoney, formatAmount, formatDate, formatMonth, formatTime, settings }
}
