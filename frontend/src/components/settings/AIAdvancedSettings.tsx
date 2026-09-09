import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import toast from 'react-hot-toast'
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
 * The knobs most households never touch, behind one disclosure: thinking
 * mode, the receipt timeout, and pass-through Ollama options JSON — how
 * model-specific tuning works without model-specific code.
 *
 * A full-width row with a border rather than a text link, because the link
 * version was invisible: people asked where the model options had gone
 * while standing on the page that had them.
 */
export function AIAdvancedSettings() {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const get = (key: string) => settings?.find((s) => s.key === key)?.value ?? ''

  const [open, setOpen] = useState(false)
  // Drafts that are null until typed in: each field shows the server value,
  // and a local edit wins until it is saved. No sync effect, so nothing can
  // freeze at a first render.
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const draft = (key: string, fallback: string) => drafts[key] ?? (get(key) || fallback)
  const setDraft = (key: string, value: string) => setDrafts((d) => ({ ...d, [key]: value }))
  const editOptions = draft('ollama_options', '{}')
  const editVisionOptions = draft('ollama_vision_options', '{}')
  const editTimeout = draft('ai_vision_timeout_s', '300')

  async function save(key: string, value: string) {
    try {
      await updateSetting.mutateAsync({ key, value })
      setDrafts(({ [key]: _saved, ...rest }) => rest)
      toast.success('Saved')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Save failed')
    }
  }

  const optionsValid = isJsonObject(editOptions)
  const visionOptionsValid = isJsonObject(editVisionOptions)

  return (
    <div className="ai-settings__disclosure">
      <button
        type="button"
        className="ai-settings__disclosure-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="ai-advanced-body"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="ai-settings__disclosure-label">Advanced</span>
        <span className="ai-settings__disclosure-hint">
          Thinking mode, receipt timeout, raw Ollama options
        </span>
      </button>

      {open && (
        <div className="ai-settings__disclosure-body" id="ai-advanced-body">
          <div className="settings-row">
            <div>
              <label className="settings-row__label" htmlFor="ai-thinking">
                Thinking
              </label>
              <div className="settings-row__desc">
                Auto enables thinking only when the model reports supporting it.
              </div>
            </div>
            <select
              id="ai-thinking"
              className="settings-select"
              value={get('ai_thinking') || 'auto'}
              onChange={(e) => void save('ai_thinking', e.target.value)}
            >
              <option value="auto">Auto (recommended)</option>
              <option value="on">Always on</option>
              <option value="off">Off</option>
            </select>
          </div>

          <div className="settings-row">
            <div>
              <label className="settings-row__label" htmlFor="ai-vision-timeout">
                Receipt scan timeout
              </label>
              <div className="settings-row__desc">
                Bigger models on modest hardware need more patience.
              </div>
            </div>
            <div className="ai-settings__inline">
              <input
                id="ai-vision-timeout"
                type="number"
                inputMode="numeric"
                min={10}
                className="settings-input ai-settings__timeout"
                value={editTimeout}
                onChange={(e) => setDraft('ai_vision_timeout_s', e.target.value)}
              />
              <span className="ai-panel__retention-unit">seconds</span>
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
              <label className="settings-row__label" htmlFor="ai-options">
                Ollama options (all tasks)
              </label>
              <div className="settings-row__desc">
                JSON passed straight to Ollama's options — see your model's page for supported keys,
                e.g. {'{"temperature": 0.2}'}. The assistant's context window is set above and wins
                over a num_ctx here.
              </div>
            </div>
            <textarea
              id="ai-options"
              className={`ai-settings__json ${optionsValid ? '' : 'ai-settings__json--invalid'}`}
              value={editOptions}
              onChange={(e) => setDraft('ollama_options', e.target.value)}
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
              <label className="settings-row__label" htmlFor="ai-vision-options">
                Extra options for receipt scans
              </label>
              <div className="settings-row__desc">
                Merged on top for receipt scans only — e.g. image-token settings.
              </div>
            </div>
            <textarea
              id="ai-vision-options"
              className={`ai-settings__json ${visionOptionsValid ? '' : 'ai-settings__json--invalid'}`}
              value={editVisionOptions}
              onChange={(e) => setDraft('ollama_vision_options', e.target.value)}
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
