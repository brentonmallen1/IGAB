import { useMemo } from 'react'
import { useGuideStore } from '../../stores/guideStore'
import { useGuideSignalMap } from './useGuideSignalMap'
import { useCheckupLeds } from './useCheckupLeds'
import { roadmapPosition, type RoadmapPosition } from './roadmapPosition'

/**
 * The roadmap cursor, from the same payloads the views already read — the
 * signals, the checkup's step markers, the reader's marks and answers. No
 * extra request. `ready` is false while the signals are still loading, so a
 * view does not act on a cursor computed from half the evidence.
 */
export function useRoadmapPosition(): RoadmapPosition & { ready: boolean } {
  const guide = useGuideSignalMap()
  const { leds } = useCheckupLeds()
  const answers = useGuideStore((s) => s.answers)
  const { progress, signals, isLoading } = guide

  return useMemo(
    () => ({ ...roadmapPosition({ progress, leds, signals, answers }), ready: !isLoading }),
    [progress, leds, signals, answers, isLoading]
  )
}
