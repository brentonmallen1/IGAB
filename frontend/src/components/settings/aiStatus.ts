import { useAIStatus } from '../../api/ai'
import { useSettings } from '../../api/settings'

export type AIStatusTone = 'disabled' | 'loading' | 'connected' | 'error'

export const AI_STATUS_LABEL: Record<AIStatusTone, string> = {
  disabled: 'Disabled',
  loading: 'Checking…',
  connected: 'Connected',
  error: 'Not connected',
}

/** The one reading of "is AI up": switched off beats everything, then an
 *  answer still on its way, then what the answer said. */
export function aiStatusTone(
  enabled: boolean,
  checking: boolean,
  available: boolean | undefined
): AIStatusTone {
  if (!enabled) return 'disabled'
  if (checking) return 'loading'
  return available ? 'connected' : 'error'
}

/** The tone from the live settings and status queries — the System page's
 *  nav hint and the section's title badge both read this, so they agree. */
export function useAIStatusTone(): AIStatusTone {
  const { data: appSettings } = useSettings()
  const aiStatus = useAIStatus()
  const enabled = appSettings?.find((s) => s.key === 'ai_enabled')?.value === 'true'
  return aiStatusTone(enabled, aiStatus.isLoading, aiStatus.data?.available)
}
