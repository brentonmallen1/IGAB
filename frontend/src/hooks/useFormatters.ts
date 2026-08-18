import { useCallback } from 'react'
import { useAppStore } from '../stores/appStore'
import { useFormatSettings } from '../contexts/FormatContext'
import { formatMoneyWithOptions, formatAmountWithOptions, getCurrencySymbol } from '../utils/money'
import {
  formatDateTimeWithOptions,
  formatDateWithOptions,
  formatMonthWithOptions,
  formatTimeWithOptions,
} from '../utils/dates'

/** Privacy-mode mask: sign and digits hidden, so overspending can't be inferred. */
const MASK = '••••'

export function useFormatters() {
  const settings = useFormatSettings()
  const privacyMode = useAppStore((s) => s.privacyMode)

  const formatMoney = useCallback(
    (amount: number) =>
      privacyMode
        ? `${getCurrencySymbol(settings.currencyCode)}${MASK}`
        : formatMoneyWithOptions(amount, settings.currencyCode, settings.numberFormat),
    [privacyMode, settings.currencyCode, settings.numberFormat]
  )

  const formatAmount = useCallback(
    (amount: number) =>
      privacyMode ? MASK : formatAmountWithOptions(amount, settings.numberFormat),
    [privacyMode, settings.numberFormat]
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

  /** Full ISO datetime → local "Aug 17, 2026 1:53 PM" (per date/time format). */
  const formatDateTime = useCallback(
    (isoStr: string) => formatDateTimeWithOptions(isoStr, settings.dateFormat, settings.timeFormat),
    [settings.dateFormat, settings.timeFormat]
  )

  return {
    formatMoney,
    formatAmount,
    formatDate,
    formatMonth,
    formatTime,
    formatDateTime,
    settings,
    privacyMode,
  }
}
