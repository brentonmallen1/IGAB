import { useMemo } from 'react'
import { useAppStore } from '../../stores/appStore'
import { useGuideCheckup, useGuideOverview } from '../../api/guide'
import { ledStages } from './checkupLeds'
import type { StageId } from '../../content/roadmap'
import type { CheckupFinding } from '../../api/guide'

/**
 * The quiet markers on roadmap steps, from the same payload the Checkup tab
 * and the health report read — one computation, three surfaces.
 *
 * Fetches only once the preferences say reviews are on. That is one extra
 * round trip on first paint, and it is what makes "off" mean off: no request
 * to the checkup endpoint is ever made for a household that switched it off.
 */
export function useCheckupLeds(): {
  enabled: boolean
  leds: Map<StageId, CheckupFinding>
} {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  const prefs = overview?.preferences
  const enabled = !!prefs?.personalization && !!prefs?.checkup
  const { data } = useGuideCheckup(budgetId, enabled)

  return useMemo(() => {
    if (!enabled || !data?.enabled) return { enabled, leds: new Map() }
    return { enabled, leds: ledStages(data.findings, overview?.progress ?? {}) }
  }, [enabled, data, overview])
}
