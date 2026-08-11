import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, Sparkles, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAIStatus } from '../../api/ai'
import { useParseNLTransaction, type NLDraft } from '../../api/aiJobs'
import { useSpeechRecognition } from '../../hooks/useSpeechRecognition'
import { TransactionEditor, type EditorDraft } from '../transactions/TransactionEditor/TransactionEditor'
import './NLQuickEntry.css'

interface Props {
  budgetId: string
  /** Fixed account context when opened from an account register. */
  accountId?: string | null
  onClose: () => void
}

function draftToEditorDraft(draft: NLDraft, jobId: string): EditorDraft {
  const amount = parseFloat(draft.amount)
  const abs = Math.abs(amount).toFixed(2)
  return {
    date: draft.date,
    payeeName: draft.payee ?? undefined,
    categoryId: draft.category_id,
    memo: draft.memo ?? undefined,
    outflow: amount < 0 ? abs : undefined,
    inflow: amount >= 0 ? abs : undefined,
    aiJobId: jobId,
  }
}

/**
 * Natural-language transaction entry: type or dictate "coffee starbucks 5.50
 * yesterday", confirm the text, and the parsed draft opens in the normal
 * add-transaction editor — one flow regardless of how the words got here.
 */
export function NLQuickEntry({ budgetId, accountId = null, onClose }: Props) {
  const aiStatus = useAIStatus()
  const parse = useParseNLTransaction(budgetId)
  const speech = useSpeechRecognition()
  const [text, setText] = useState('')
  const [editorDraft, setEditorDraft] = useState<EditorDraft | null>(null)
  const [micHidden, setMicHidden] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Dictated words flow into the editable input — never auto-submitted
  useEffect(() => {
    if (speech.transcript) setText(speech.transcript)
  }, [speech.transcript])

  // Permission denied / service unavailable: hide the mic for this session,
  // the text path is unaffected
  useEffect(() => {
    if (speech.error) {
      setMicHidden(true)
      toast.error('Microphone unavailable — type instead')
    }
  }, [speech.error])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  async function handleParse() {
    const trimmed = text.trim()
    if (!trimmed) return
    try {
      const result = await parse.mutateAsync(trimmed)
      setEditorDraft(draftToEditorDraft(result.draft, result.job_id))
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      toast.error(detail ?? 'Could not parse that — try rephrasing')
    }
  }

  if (editorDraft) {
    return (
      <TransactionEditor
        budgetId={budgetId}
        accountId={accountId}
        transaction={null}
        initialDraft={editorDraft}
        onClose={() => {
          setEditorDraft(null)
          onClose()
        }}
      />
    )
  }

  if (aiStatus.data && !aiStatus.data.available) return null

  const display = speech.interim ? `${text} ${speech.interim}`.trim() : text

  return (
    <div
      className="nl-entry-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="nl-entry" role="dialog" aria-modal aria-label="AI transaction entry">
        <div className="nl-entry__header">
          <Sparkles size={14} />
          <span>Describe a transaction</span>
          <button className="nl-entry__close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <form
          className="nl-entry__row"
          onSubmit={(e) => {
            e.preventDefault()
            void handleParse()
          }}
        >
          <input
            ref={inputRef}
            className={`nl-entry__input ${speech.interim ? 'nl-entry__input--interim' : ''}`}
            type="text"
            value={display}
            onChange={(e) => setText(e.target.value)}
            placeholder='e.g. "coffee at Starbucks 5.50 yesterday"'
            disabled={parse.isPending}
          />
          {speech.supported && !micHidden && (
            <button
              type="button"
              className={`nl-entry__mic ${speech.listening ? 'nl-entry__mic--listening' : ''}`}
              onClick={() => (speech.listening ? speech.stop() : speech.start())}
              aria-label={speech.listening ? 'Stop dictation' : 'Dictate'}
              title={speech.listening ? 'Stop dictation' : 'Dictate'}
            >
              {speech.listening ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
          )}
          <button
            type="submit"
            className="nl-entry__parse"
            disabled={!text.trim() || parse.isPending}
          >
            {parse.isPending ? 'Parsing…' : 'Parse'}
          </button>
        </form>
        <p className="nl-entry__hint">
          You'll confirm every detail before anything is saved.
        </p>
      </div>
    </div>
  )
}
