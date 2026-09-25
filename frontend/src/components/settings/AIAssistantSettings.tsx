import { useState } from 'react'
import toast from 'react-hot-toast'
import { useSettings, useUpdateSetting } from '../../api/settings'
import './AISettings.css'

/**
 * How the chat panel runs: how long an answer may take. The context window
 * it asks for is every model call's, so it lives with the models
 * (AIContextWindow).
 */
export function AIAssistantSettings() {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const get = (key: string) => settings?.find((s) => s.key === key)?.value ?? ''

  // A draft that is null until typed in: the field shows the server value,
  // and a local edit wins until it is saved and the server catches up. No
  // effect, so nothing can freeze at a first render.
  const [timeoutDraft, setTimeoutDraft] = useState<string | null>(null)
  const editTimeout = timeoutDraft ?? (get('ai_chat_timeout_s') || '120')

  async function save(key: string, value: string) {
    try {
      await updateSetting.mutateAsync({ key, value })
      setTimeoutDraft(null)
      toast.success('Saved')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Save failed')
    }
  }

  return (
    <div className="settings-subsection">
      <div className="settings-subsection__title">Assistant</div>

      <div className="settings-row">
        <div>
          <label className="settings-row__label" htmlFor="ai-chat-timeout">
            Answer timeout
          </label>
          <div className="settings-row__desc">
            An answer can take several round trips while it looks things up.
          </div>
        </div>
        <div className="ai-settings__inline">
          <input
            id="ai-chat-timeout"
            type="number"
            inputMode="numeric"
            min={10}
            className="settings-input ai-settings__timeout"
            value={editTimeout}
            onChange={(e) => setTimeoutDraft(e.target.value)}
          />
          <span className="ai-panel__retention-unit">seconds</span>
          <button
            className="settings-btn settings-btn--secondary"
            onClick={() => void save('ai_chat_timeout_s', editTimeout)}
            disabled={!/^[1-9]\d*$/.test(editTimeout) || updateSetting.isPending}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
