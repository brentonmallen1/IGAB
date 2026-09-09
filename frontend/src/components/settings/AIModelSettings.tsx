import { useState } from 'react'
import { AlertTriangle, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAIStatus, useOllamaModels, type OllamaModel } from '../../api/ai'
import { useSettings, useUpdateSetting } from '../../api/settings'
import { ModelSelect } from './ModelSelect'
import { formatTokens, type Capability } from './modelChoice'
import './AISettings.css'

/**
 * Which model does which job.
 *
 * Three pickers of one shape: the main model, and an override each for
 * receipts (needs vision) and the assistant (needs tools). Under each
 * override is the line that matters — which model will *actually* do the
 * job, resolved server-side through the real fallback chain, and whether
 * the server says it can. The controls can be wrong about that; the line
 * cannot, because it comes from the same probe the worker gates on.
 */
export function AIModelSettings() {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const { data: status } = useAIStatus()
  const { data: models, refetch, isFetching } = useOllamaModels()

  const get = (key: string) => settings?.find((s) => s.key === key)?.value ?? ''
  const mainModel = get('ollama_model')

  async function save(key: string, value: string, label: string): Promise<boolean> {
    try {
      await updateSetting.mutateAsync({ key, value })
      toast.success(value ? `${label} set to ${value}` : `${label} uses the main model`)
      return true
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Save failed')
      return false
    }
  }

  return (
    <div className="settings-subsection">
      <div className="settings-subsection__title">Models</div>

      <div className="settings-row">
        <div>
          <label className="settings-row__label" htmlFor="ai-main-model">
            Main model
          </label>
          <div className="settings-row__desc">
            Category suggestions, natural-language entry, and any job without its own model below.
          </div>
        </div>
        <div className="ai-panel__actions">
          <ModelSelect
            id="ai-main-model"
            value={mainModel}
            models={models}
            onChange={(name) => void save('ollama_model', name, 'Main model')}
          />
          <button
            className="settings-btn settings-btn--secondary"
            onClick={() => void refetch()}
            disabled={isFetching}
            title="Ask Ollama for its model list again"
          >
            {isFetching ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {status?.available && models && models.length === 0 && !isFetching && (
        <div className="ai-panel__empty">
          No models found. Pull at least one model in Ollama, then refresh.
        </div>
      )}

      <OverrideRow
        settingKey="ollama_vision_model"
        serverValue={get('ollama_vision_model')}
        models={models}
        require="vision"
        label="Use a different model for receipts"
        desc="Receipt scanning needs a vision-capable model. Off = the main model reads receipts; on = pick a dedicated one, such as a small OCR model."
        onSave={(value) => save('ollama_vision_model', value, 'Receipt model')}
        status={
          status && (
            <GroundTruth
              testId="receipt-model-line"
              lead="Receipts are scanned by"
              model={status.receipt_model}
              capability="vision"
              verdict={status.receipt_model_vision}
            />
          )
        }
      />

      <OverrideRow
        settingKey="ollama_chat_model"
        serverValue={get('ollama_chat_model')}
        models={models}
        require="tools"
        label="Use a different model for the assistant"
        desc="The assistant looks figures up with tools, so its model must support tool calling. Off = the main model answers; on = pick one that does."
        onSave={(value) => save('ollama_chat_model', value, 'Assistant model')}
        status={
          status && (
            <GroundTruth
              testId="assistant-model-line"
              lead="The assistant uses"
              model={status.chat_model}
              capability="tools"
              verdict={status.chat_model_tools}
              extra={
                status.chat_num_ctx && status.chat_model_context_length
                  ? `asks for ${formatTokens(status.chat_num_ctx)} of its ${formatTokens(status.chat_model_context_length)} context`
                  : null
              }
            />
          )
        }
      />
    </div>
  )
}

/**
 * A toggle-and-picker pair for an optional model override.
 *
 * The toggle reflects the SERVER, re-synced whenever the server value
 * changes — a completed save, or a change made on another device — while a
 * local flip wins in between. A once-only sync once left this OFF with a
 * vision model silently set in the DB: the exact lie that let a non-vision
 * model process receipts unnoticed.
 */
function OverrideRow({
  settingKey,
  serverValue,
  models,
  require,
  label,
  desc,
  onSave,
  status,
}: {
  settingKey: string
  serverValue: string
  models: OllamaModel[] | undefined
  require: Capability
  label: string
  desc: string
  onSave: (value: string) => Promise<boolean>
  status: React.ReactNode
}) {
  const [lastServer, setLastServer] = useState<string | null>(null)
  const [on, setOn] = useState(false)
  if (serverValue !== lastServer) {
    setLastServer(serverValue)
    setOn(!!serverValue)
  }

  async function toggle(enabled: boolean) {
    setOn(enabled)
    if (!enabled && serverValue) {
      // The DB still holds the old value until the save lands — and if it
      // fails, showing OFF would be a lie.
      if (!(await onSave(''))) setOn(true)
    }
  }

  const selectId = `${settingKey}-select`
  return (
    <>
      <div className="settings-row">
        <div>
          <div className="settings-row__label">{label}</div>
          <div className="settings-row__desc">{desc}</div>
        </div>
        <label className="ai-settings__toggle">
          <input
            type="checkbox"
            checked={on}
            onChange={(e) => void toggle(e.target.checked)}
            aria-label={label}
          />
          <span />
        </label>
      </div>
      {on && (
        <div className="settings-row ai-settings__override-pick">
          <label className="settings-row__label" htmlFor={selectId}>
            {require === 'vision' ? 'Receipt model' : 'Assistant model'}
          </label>
          <ModelSelect
            id={selectId}
            value={serverValue}
            models={models}
            require={require}
            onChange={(name) => void onSave(name)}
          />
        </div>
      )}
      {/* Always visible, not gated on the toggle: this line is the ground
          truth for which model does the job, whatever the controls claim. */}
      {status}
    </>
  )
}

function GroundTruth({
  testId,
  lead,
  model,
  capability,
  verdict,
  extra,
}: {
  testId: string
  lead: string
  model: string
  capability: Capability
  /** true/false from the server; null = unknown, which is never a warning. */
  verdict: boolean | null | undefined
  extra?: string | null
}) {
  return (
    <div className="ai-settings__ground-truth" data-testid={testId}>
      {lead} <strong>{model}</strong>
      {verdict === false && (
        <span className="ai-settings__ground-truth-warning">
          <AlertTriangle size={12} aria-hidden />
          this model does not support {capability}
        </span>
      )}
      {verdict === true && (
        <span className="ai-settings__ground-truth-ok">
          <CheckCircle size={12} aria-hidden />
          {capability}
        </span>
      )}
      {extra && <span className="ai-settings__ground-truth-extra"> · {extra}</span>}
    </div>
  )
}
