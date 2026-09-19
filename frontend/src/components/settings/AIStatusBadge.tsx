import { CheckCircle, Loader2, XCircle } from 'lucide-react'
import { AI_STATUS_LABEL, useAIStatusTone } from './aiStatus'
import './AISettingsPanel.css'

/** The connection badge beside the AI section's title. */
export function AIStatusBadge() {
  const tone = useAIStatusTone()
  return (
    <span className={`ai-panel__status ai-panel__status--${tone}`}>
      {tone === 'loading' && <Loader2 size={12} className="spin" aria-hidden="true" />}
      {tone === 'connected' && <CheckCircle size={12} aria-hidden="true" />}
      {tone === 'error' && <XCircle size={12} aria-hidden="true" />}
      {AI_STATUS_LABEL[tone]}
    </span>
  )
}
