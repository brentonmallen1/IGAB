import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { sameOllamaModel, useAIStatus, useOllamaModels } from '../../api/ai'
import { useSettings, useUpdateSetting } from '../../api/settings'
import './AISettings.css'

function isJsonObject(value: string): boolean {
  try {
    const parsed = JSON.parse(value || '{}')
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
  } catch {
    return false
  }
}

/**
 * Model-agnostic knobs: a vision-model override for receipt scanning, the
 * thinking mode (auto follows the model's advertised capabilities), and
 * pass-through Ollama options JSON — how model-specific tuning (image
 * tokens, num_ctx, ...) works without model-specific code.
 */
export function AIAdvancedSettings() {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const aiStatus = useAIStatus()
  const { data: models } = useOllamaModels()

  const get = (key: string) => settings?.find((s) => s.key === key)?.value ?? ''

  const visionModel = get('ollama_vision_model')
  const [useVisionOverride, setUseVisionOverride] = useState(false)
  const [editVisionModel, setEditVisionModel] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [editOptions, setEditOptions] = useState('')
  const [editVisionOptions, setEditVisionOptions] = useState('')
  const [editTimeout, setEditTimeout] = useState('')

  // Sync the vision pair whenever the SERVER value changes — initial load, a
  // completed save, or a change made on another device — while local edits
  // win in between (same pattern as Combobox). The old once-only effect left
  // this state frozen at its first value, which could render the toggle OFF
  // with a vision model silently set in the DB: the exact lie that let a
  // non-vision model process receipts unnoticed.
  const [lastServerVisionModel, setLastServerVisionModel] = useState<string | null>(null)
  if (settings && visionModel !== lastServerVisionModel) {
    setLastServerVisionModel(visionModel)
    setUseVisionOverride(!!visionModel)
    setEditVisionModel(visionModel)
  }

  useEffect(() => {
    if (!settings) return
    setEditOptions(get('ollama_options') || '{}')
    setEditVisionOptions(get('ollama_vision_options') || '{}')
    setEditTimeout(get('ai_vision_timeout_s') || '300')
    // Free-text editors sync from the server once loaded; local edits win
    // afterwards (unlike the vision pair above, they are inputs, not state
    // indicators).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings === undefined])

  async function save(key: string, value: string): Promise<boolean> {
    try {
      await updateSetting.mutateAsync({ key, value })
      toast.success('Saved')
      return true
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      toast.error(detail ?? 'Save failed')
      return false
    }
  }

  async function toggleVisionOverride(enabled: boolean) {
    setUseVisionOverride(enabled)
    if (!enabled) {
      const previous = editVisionModel
      setEditVisionModel('')
      if (!(await save('ollama_vision_model', ''))) {
        // The DB still holds the old value — showing OFF would be a lie.
        setUseVisionOverride(true)
        setEditVisionModel(previous)
      }
    }
  }

  // What will actually scan receipts, resolved server-side through the real
  // fallback chain (override → main model). Warn only when Ollama knows the
  // model and it lacks vision — an unknown model (Ollama down, not pulled)
  // is a different problem and must not read as "misconfigured".
  const receiptModel = aiStatus.data?.receipt_model ?? null
  const receiptModelInfo = models?.find((m) => sameOllamaModel(m.name, receiptModel))
  const receiptModelLacksVision =
    !!receiptModelInfo && !receiptModelInfo.capabilities.includes('vision')

  const optionsValid = isJsonObject(editOptions)
  const visionOptionsValid = isJsonObject(editVisionOptions)

  return (
    <div className="ai-settings">
      <div className="settings-row">
        <div>
          <div className="settings-row__label">Use a different model for vision tasks</div>
          <div className="settings-row__desc">
            Receipt scanning needs a vision-capable model. Off = the main model handles
            everything; on = pick a dedicated one (e.g. a small OCR model).
          </div>
        </div>
        <label className="ai-settings__toggle">
          <input
            type="checkbox"
            checked={useVisionOverride}
            onChange={(e) => void toggleVisionOverride(e.target.checked)}
          />
          <span />
        </label>
      </div>
      {/* Always visible, not gated on the toggle: this line is the ground
          truth for "which model reads my receipts", whatever the controls
          above claim. */}
      {receiptModel && (
        <div className="ai-settings__receipt-model" data-testid="receipt-model-line">
          Receipts are scanned by <strong>{receiptModel}</strong>
          {receiptModelLacksVision && (
            <span className="ai-settings__receipt-model-warning">
              <AlertTriangle size={12} aria-hidden />
              this model does not support vision
            </span>
          )}
        </div>
      )}
      {useVisionOverride && (
        <div className="settings-row">
          <div className="settings-row__label">Vision model</div>
          <div className="ai-settings__inline">
            <input
              type="text"
              className="settings-input"
              value={editVisionModel}
              onChange={(e) => setEditVisionModel(e.target.value)}
              placeholder="e.g. gemma4, moondream"
            />
            <button
              className="settings-btn settings-btn--secondary"
              onClick={() => void save('ollama_vision_model', editVisionModel.trim())}
              disabled={updateSetting.isPending}
            >
              Save
            </button>
          </div>
        </div>
      )}

      <div className="settings-row">
        <div>
          <div className="settings-row__label">Thinking</div>
          <div className="settings-row__desc">
            Auto enables thinking only when the model reports supporting it.
          </div>
        </div>
        <select
          className="ai-settings__select"
          value={get('ai_thinking') || 'auto'}
          onChange={(e) => void save('ai_thinking', e.target.value)}
        >
          <option value="auto">Auto (recommended)</option>
          <option value="on">Always on</option>
          <option value="off">Off</option>
        </select>
      </div>

      <button
        className="ai-settings__collapse-toggle"
        onClick={() => setAdvancedOpen((v) => !v)}
      >
        {advancedOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        Advanced model options
      </button>

      {advancedOpen && (
        <div className="ai-settings__advanced">
          <div className="settings-row settings-row--stacked">
            <div>
              <div className="settings-row__label">Vision request timeout (seconds)</div>
              <div className="settings-row__desc">
                Bigger models on modest hardware need more patience.
              </div>
            </div>
            <div className="ai-settings__inline">
              <input
                type="number"
                inputMode="numeric"
                min={10}
                className="settings-input ai-settings__timeout"
                value={editTimeout}
                onChange={(e) => setEditTimeout(e.target.value)}
              />
              <button
                className="settings-btn settings-btn--secondary"
                onClick={() => void save('ai_vision_timeout_s', editTimeout)}
                disabled={!/^[1-9]\d*$/.test(editTimeout)}
              >
                Save
              </button>
            </div>
          </div>

          <div className="settings-row settings-row--stacked">
            <div>
              <div className="settings-row__label">Ollama options (all tasks)</div>
              <div className="settings-row__desc">
                JSON passed straight to Ollama's options — see your model's page for
                supported keys, e.g. {'{"num_ctx": 8192}'}.
              </div>
            </div>
            <textarea
              className={`ai-settings__json ${optionsValid ? '' : 'ai-settings__json--invalid'}`}
              value={editOptions}
              onChange={(e) => setEditOptions(e.target.value)}
              rows={3}
              spellCheck={false}
            />
            <div className="ai-settings__json-actions">
              {!optionsValid && <span className="ai-settings__json-error">Not a JSON object</span>}
              <button
                className="settings-btn settings-btn--secondary"
                onClick={() => void save('ollama_options', editOptions.trim() || '{}')}
                disabled={!optionsValid || updateSetting.isPending}
              >
                Save
              </button>
            </div>
          </div>

          <div className="settings-row settings-row--stacked">
            <div>
              <div className="settings-row__label">Extra options for vision tasks</div>
              <div className="settings-row__desc">
                Merged on top for receipt scans only — e.g. image-token settings.
              </div>
            </div>
            <textarea
              className={`ai-settings__json ${visionOptionsValid ? '' : 'ai-settings__json--invalid'}`}
              value={editVisionOptions}
              onChange={(e) => setEditVisionOptions(e.target.value)}
              rows={3}
              spellCheck={false}
            />
            <div className="ai-settings__json-actions">
              {!visionOptionsValid && (
                <span className="ai-settings__json-error">Not a JSON object</span>
              )}
              <button
                className="settings-btn settings-btn--secondary"
                onClick={() => void save('ollama_vision_options', editVisionOptions.trim() || '{}')}
                disabled={!visionOptionsValid || updateSetting.isPending}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
