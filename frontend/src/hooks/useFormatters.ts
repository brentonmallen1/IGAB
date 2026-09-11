import { useCallback } from 'react'
import { useAppStore } from '../stores/appStore'
import { useFormatSettings } from '../contexts/FormatContext'
import {
  formatMoneyWithOptions,
  formatAmountWithOptions,
  getCurrencySymbol,
  moneyOrDash,
  PRIVACY_MASK,
} from '../utils/money'
import {
  formatDateTimeWithOptions,
  formatDateWithOptions,
  formatDayMonthWithOptions,
  formatMonthShortWithOptions,
  formatMonthWithOptions,
  formatTimeWithOptions,
} from '../utils/dates'

export function useFormatters() {
  const settings = useFormatSettings()
  const privacyMode = useAppStore((s) => s.privacyMode)

  const formatMoney = useCallback(
    (amount: number) =>
      privacyMode
        ? `${getCurrencySymbol(settings.currencyCode)}${PRIVACY_MASK}`
        : formatMoneyWithOptions(amount, settings.currencyCode, settings.numberFormat),
    [privacyMode, settings.currencyCode, settings.numberFormat]
  )

  /** `formatMoney`, or an em dash for a figure that does not exist. */
  const formatMoneyOrDash = useCallback(
    (amount: number | null | undefined) => moneyOrDash(amount, formatMoney),
    [formatMoney]
  )

  const formatAmount = useCallback(
    (amount: number) =>
      privacyMode ? PRIVACY_MASK : formatAmountWithOptions(amount, settings.numberFormat),
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

  /** Short day + month ("Sep 10") for a dense chart axis. */
  const formatDayMonth = useCallback(
    (dateStr: string) => formatDayMonthWithOptions(dateStr, settings.dateFormat),
    [settings.dateFormat]
  )

  /** Short month + 2-digit year ("Sep 26") for a dense chart axis. */
  const formatMonthShort = useCallback(
    (monthStr: string) => formatMonthShortWithOptions(monthStr, settings.dateFormat),
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
    formatMoneyOrDash,
    formatAmount,
    formatDate,
    formatMonth,
    formatMonthShort,
    formatDayMonth,
    formatTime,
    formatDateTime,
    settings,
    privacyMode,
  }
}
