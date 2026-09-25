import toast from 'react-hot-toast'
import { useAIStatus } from '../../api/ai'
import { useSettings, useUpdateSetting } from '../../api/settings'
import { autoWindowLabel, formatTokens, sharedContextChoices } from './modelChoice'
import './AISettings.css'

/**
 * How much context every model call asks for: receipt scans, suggestions and
 * the assistant alike, one setting sized per model on the server.
 *
 * It lived under the assistant until receipts needed it too. A scan that
 * asked for nothing got Ollama's default, 4,096 tokens on a GPU under 24 GB,
 * and a thinking model spent it before finishing its answer. The key is still
 * `ai_chat_num_ctx`; only its reach grew.
 */
export function AIContextWindow() {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const { data: status } = useAIStatus()

  const windowSetting = settings?.find((s) => s.key === 'ai_chat_num_ctx')?.value || 'auto'
  const choices = sharedContextChoices([
    status?.receipt_model_context_length,
    status?.chat_model_context_length,
  ])
  // A saved size the models cannot all take stays listed, so the control
  // never shows "auto" for a setting that is a number.
  const savedSize = /^\d+$/.test(windowSetting) ? Number(windowSetting) : null
  const options = savedSize && !choices.includes(savedSize) ? [...choices, savedSize] : choices

  async function save(value: string) {
    try {
      await updateSetting.mutateAsync({ key: 'ai_chat_num_ctx', value })
      toast.success('Saved')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Save failed')
    }
  }

  return (
    <div className="settings-row">
      <div>
        <label className="settings-row__label" htmlFor="ai-context-window">
          Context window
        </label>
        <div className="settings-row__desc">
          How much a model can hold at once — for a receipt, the categories, the image, its thinking
          and its answer. Every AI call asks for this, so the model is not reloaded between a scan
          and the assistant. Auto uses what each model supports, up to 32k. Larger windows use more
          memory on the Ollama host. Each model's line above says what it is given.
        </div>
      </div>
      <select
        id="ai-context-window"
        className="settings-select"
        value={savedSize ? String(savedSize) : 'auto'}
        onChange={(e) => void save(e.target.value)}
      >
        <option value="auto">
          {autoWindowLabel([status?.receipt_num_ctx, status?.chat_num_ctx])}
        </option>
        {options.map((n) => (
          <option key={n} value={String(n)}>
            {formatTokens(n)} tokens
          </option>
        ))}
      </select>
    </div>
  )
}
