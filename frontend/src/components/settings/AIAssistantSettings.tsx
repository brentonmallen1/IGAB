import { useState } from 'react'
import toast from 'react-hot-toast'
import { useAIStatus } from '../../api/ai'
import { useSettings, useUpdateSetting } from '../../api/settings'
import { contextChoices, formatTokens } from './modelChoice'
import './AISettings.css'

/**
 * How the chat panel runs: how much context it asks the model for, and how
 * long an answer may take.
 *
 * The window is a real setting because Ollama's default is small enough to
 * drop the system prompt on a big budget, and because the whole 128k a
 * model advertises is not free — the server allocates memory for it.
 */
export function AIAssistantSettings() {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const { data: status } = useAIStatus()
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

  const modelMax = status?.chat_model_context_length ?? null
  const windowSetting = get('ai_chat_num_ctx') || 'auto'
  const choices = contextChoices(modelMax)
  // A saved size the current model cannot take stays listed, so the control
  // never shows "auto" for a setting that is a number.
  const savedSize = /^\d+$/.test(windowSetting) ? Number(windowSetting) : null
  const options = savedSize && !choices.includes(savedSize) ? [...choices, savedSize] : choices
  const autoLabel = status?.chat_num_ctx
    ? `Auto (${formatTokens(status.chat_num_ctx)})`
    : 'Auto (sized from the model)'

  return (
    <div className="settings-subsection">
      <div className="settings-subsection__title">Assistant</div>

      <div className="settings-row">
        <div>
          <label className="settings-row__label" htmlFor="ai-chat-window">
            Context window
          </label>
          <div className="settings-row__desc">
            How much the model can hold at once: your question, the history, and everything it
            looked up. Auto uses what the model supports, up to 32k. Larger windows use more memory
            on the Ollama host.
            {modelMax ? ` This model supports up to ${formatTokens(modelMax)}.` : ''}
          </div>
        </div>
        <select
          id="ai-chat-window"
          className="settings-select"
          value={savedSize ? String(savedSize) : 'auto'}
          onChange={(e) => void save('ai_chat_num_ctx', e.target.value)}
        >
          <option value="auto">{autoLabel}</option>
          {options.map((n) => (
            <option key={n} value={String(n)}>
              {formatTokens(n)} tokens
            </option>
          ))}
        </select>
      </div>

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
