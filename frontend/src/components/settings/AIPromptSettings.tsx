import { useState } from 'react'
import { ChevronDown, ChevronUp, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useResetSetting, useSettings, useUpdateSetting } from '../../api/settings'
import './AISettings.css'

// Labels and where each prompt runs — copy about the UI, so it lives with the
// UI. Which placeholders a prompt takes is served with the setting, from the
// backend's one registry.
const PROMPT_TASKS: Array<{ key: string; label: string; usage: string }> = [
  {
    key: 'ai_prompt_receipt_gate',
    label: 'Receipt gate (is this a receipt?)',
    usage:
      'Runs first on every receipt photo — from Quick Add or the transaction editor’s Receipt tab — and decides whether the image is a receipt at all before the expensive read.',
  },
  {
    key: 'ai_prompt_receipt_extract',
    label: 'Receipt extraction',
    usage:
      'Reads a receipt photo into a draft transaction — payee, total, date, category, line items and a suggested split — once the gate has passed.',
  },
  {
    key: 'ai_prompt_nl_parse',
    label: 'Natural-language entry',
    usage:
      'Turns a typed or dictated sentence into a draft transaction: the natural-language entry in Quick Add and in the transaction editor.',
  },
  {
    key: 'ai_prompt_suggest_category',
    label: 'Category suggestion',
    usage: 'Answers the AI Suggest button beside the category field in the transaction editor.',
  },
  {
    key: 'ai_prompt_suggest_regex',
    label: 'Match pattern suggestion',
    usage:
      'Answers the AI button beside a payee’s match pattern — in the Payees page editor and the merge dialog — with up to three candidate patterns, tightest first.',
  },
]

function PromptCard({ taskKey, label, usage }: { taskKey: string; label: string; usage: string }) {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const resetSetting = useResetSetting()
  const setting = settings?.find((s) => s.key === taskKey)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<string | null>(null)

  const value = draft ?? setting?.value ?? ''
  const placeholders = setting?.placeholders ?? []
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
      <button
        className="ai-prompt-card__header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        <span className="ai-prompt-card__heading">
          <span className="ai-prompt-card__label">{label}</span>
          {/* Where it runs, visible without opening the card — a prompt you
              cannot place is one you will not dare to edit. */}
          <span className="ai-prompt-card__usage">{usage}</span>
        </span>
        {isOverridden && <span className="ai-prompt-card__edited">edited</span>}
      </button>
      {open && (
        <div className="ai-prompt-card__body">
          <div className="ai-prompt-card__placeholders">
            Placeholders:{' '}
            {placeholders.length === 0 ? (
              <em>none</em>
            ) : (
              placeholders.map((p) => <code key={p}>{p}</code>)
            )}
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
              title={
                isOverridden
                  ? 'Delete your override and use the shipped prompt'
                  : 'Discard unsaved edits'
              }
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
            Tune what the model is asked for each task; each card says where that task runs. Broken
            placeholders fall back to the default prompt rather than breaking the feature.
          </div>
        </div>
      </div>
      {PROMPT_TASKS.map((t) => (
        <PromptCard key={t.key} taskKey={t.key} label={t.label} usage={t.usage} />
      ))}
    </div>
  )
}
