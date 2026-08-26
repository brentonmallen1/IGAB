import { useState } from 'react'
import { ChevronDown, ChevronUp, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useResetSetting, useSettings, useUpdateSetting } from '../../api/settings'
import './AISettings.css'

const PROMPT_TASKS: Array<{ key: string; label: string; placeholders: string[] }> = [
  {
    key: 'ai_prompt_receipt_gate',
    label: 'Receipt gate (is this a receipt?)',
    placeholders: [],
  },
  {
    key: 'ai_prompt_receipt_extract',
    label: 'Receipt extraction',
    placeholders: ['{categories}', '{today}'],
  },
  {
    key: 'ai_prompt_nl_parse',
    label: 'Natural-language entry',
    placeholders: ['{text}', '{categories}', '{today}'],
  },
  {
    key: 'ai_prompt_suggest_category',
    label: 'Category suggestion',
    placeholders: ['{payee_name}', '{amount}', '{memo}', '{categories}'],
  },
]

function PromptCard({ taskKey, label, placeholders }: { taskKey: string; label: string; placeholders: string[] }) {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const resetSetting = useResetSetting()
  const setting = settings?.find((s) => s.key === taskKey)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<string | null>(null)

  const value = draft ?? setting?.value ?? ''
  const isOverridden = setting?.is_overridden === true
  const dirty = draft !== null && draft !== (setting?.value ?? '')

  async function handleSave() {
    if (draft === null) return
    await updateSetting.mutateAsync({ key: taskKey, value: draft })
    setDraft(null)
    toast.success('Prompt saved')
  }

  // Two ways back to the shipped prompt: throw away an unsaved edit, or
  // delete a saved override. Either way the default text is what remains.
  async function handleRevert() {
    if (isOverridden) {
      await resetSetting.mutateAsync(taskKey)
      toast.success('Reverted to default')
    }
    setDraft(null)
  }

  return (
    <div className="ai-prompt-card">
      <button className="ai-prompt-card__header" onClick={() => setOpen((v) => !v)}>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        <span className="ai-prompt-card__label">{label}</span>
        {isOverridden && <span className="ai-prompt-card__edited">edited</span>}
      </button>
      {open && (
        <div className="ai-prompt-card__body">
          <div className="ai-prompt-card__placeholders">
            Placeholders:{' '}
            {placeholders.map((p) => (
              <code key={p}>{p}</code>
            ))}
          </div>
          <textarea
            className="ai-settings__json ai-prompt-card__textarea"
            value={value}
            onChange={(e) => setDraft(e.target.value)}
            rows={10}
            spellCheck={false}
          />
          <div className="ai-settings__json-actions">
            <button
              className="settings-btn settings-btn--secondary"
              onClick={() => void handleRevert()}
              disabled={(!isOverridden && !dirty) || resetSetting.isPending}
              title={isOverridden ? 'Delete your override and use the shipped prompt' : 'Discard unsaved edits'}
            >
              <RotateCcw size={12} />
              {isOverridden ? 'Revert to default' : 'Discard changes'}
            </button>
            <button
              className="settings-btn settings-btn--primary"
              onClick={() => void handleSave()}
              disabled={!dirty || updateSetting.isPending}
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * The prompts behind each AI task, viewable and editable. Only overrides are
 * stored — reverting deletes the override and the shipped default returns
 * (including future improvements to it).
 */
export function AIPromptSettings() {
  return (
    <div className="ai-settings">
      <div className="settings-row">
        <div>
          <div className="settings-row__label">Prompts</div>
          <div className="settings-row__desc">
            Tune what the model is asked for each task. Broken placeholders fall back to
            the default prompt rather than breaking the feature.
          </div>
        </div>
      </div>
      {PROMPT_TASKS.map((t) => (
        <PromptCard key={t.key} taskKey={t.key} label={t.label} placeholders={t.placeholders} />
      ))}
    </div>
  )
}
