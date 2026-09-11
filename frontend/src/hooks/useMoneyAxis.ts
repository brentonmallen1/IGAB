import { useMemo } from 'react'
import { useFormatters } from './useFormatters'
import { useIsMobile } from './useMediaQuery'
import { useAppStore } from '../stores/appStore'
import { getCurrencySymbol } from '../utils/money'
import { compactMoney, MONEY_AXIS_WIDTH } from '../utils/moneyAxis'

/**
 * Props for a recharts money `<YAxis>`: the tick formatter and the width,
 * one pair for every chart. Spread it: `<YAxis {...moneyAxis} tick={…} />`.
 * Privacy mode masks the ticks the same way it masks everything else.
 */
export function useMoneyAxis(): { tickFormatter: (v: number) => string; width: number } {
  const isMobile = useIsMobile()
  const { formatMoney, settings } = useFormatters()
  const privacyMode = useAppStore((s) => s.privacyMode)
  return useMemo(() => {
    if (!isMobile)
      return { tickFormatter: (v: number) => formatMoney(v), width: MONEY_AXIS_WIDTH.desktop }
    const symbol = getCurrencySymbol(settings.currencyCode)
    return {
      tickFormatter: (v: number) => (privacyMode ? formatMoney(v) : compactMoney(v, symbol)),
      width: MONEY_AXIS_WIDTH.phone,
    }
  }, [isMobile, formatMoney, settings.currencyCode, privacyMode])
}
