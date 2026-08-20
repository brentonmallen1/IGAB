import { useEffect, useRef, useState } from 'react'
import { Mic, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAIStatus } from '../../api/ai'
import { useParseNLTransaction, type NLDraft } from '../../api/aiJobs'
import { useSpeechRecognition } from '../../hooks/useSpeechRecognition'
import type { EditorDraft } from '../transactions/TransactionEditor/TransactionEditor'
import './NLEntryForm.css'

export function draftToEditorDraft(draft: NLDraft, jobId: string): EditorDraft {
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

/** Dictation failures are usually the browser's speech *service*, not the
 * microphone — Chrome happily starts capturing and then errors when the
 * Google-hosted recognizer refuses (insecure origin) or is unreachable.
 * Say which one broke so "the browser shows recording but the app says the
 * mic is broken" can't happen. */
function speechErrorMessage(code: string): string {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return 'Dictation blocked — the browser speech service refused. It needs mic permission, and in some browsers HTTPS.'
    case 'audio-capture':
      return 'No working microphone found'
    case 'network':
      return 'Speech service unreachable — browser dictation needs an internet connection'
    default:
      return 'Dictation failed — type it instead'
  }
}

interface Props {
  budgetId: string
  /** The parsed draft, ready to prefill the add-transaction form. */
  onDraft: (draft: EditorDraft) => void
  /** Close the host surface before following a link (Settings). */
  onNavigate?: () => void
  autoFocus?: boolean
}

/**
 * The natural-language entry form: type or dictate "coffee starbucks 5.50
 * yesterday", parse, and the draft lands in the normal add-transaction form.
 * Shared by the editor's "Describe it" tab and the mobile quick-entry sheet.
 */
export function NLEntryForm({ budgetId, onDraft, onNavigate, autoFocus = true }: Props) {
  const aiStatus = useAIStatus()
  const parse = useParseNLTransaction(budgetId)
  const speech = useSpeechRecognition()
  const [text, setText] = useState('')
  const [micHidden, setMicHidden] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Dictated words flow into the editable input — never auto-submitted
  useEffect(() => {
    if (speech.transcript) setText(speech.transcript)
  }, [speech.transcript])

  // Dictation failed: say specifically what broke, then hide the mic for the
  // session — none of these codes recover without the user changing something.
  useEffect(() => {
    if (speech.error) {
      setMicHidden(true)
      toast.error(speechErrorMessage(speech.error))
    }
  }, [speech.error])

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus()
  }, [autoFocus])

  async function handleParse() {
    const trimmed = text.trim()
    if (!trimmed) return
    try {
      const result = await parse.mutateAsync(trimmed)
      onDraft(draftToEditorDraft(result.draft, result.job_id))
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      toast.error(detail ?? 'Could not parse that — try rephrasing')
    }
  }

  if (aiStatus.data && !aiStatus.data.available) {
    return (
      <div className="nl-form__unavailable">
        <Sparkles size={20} />
        <p>Describing a transaction requires a configured Ollama server.</p>
        <Link to="/settings" className="nl-form__link" onClick={onNavigate}>
          Configure AI in Settings
        </Link>
      </div>
    )
  }

  const display = speech.interim ? `${text} ${speech.interim}`.trim() : text

  return (
    <div className="nl-form">
      <div className="nl-form__row">
        <input
          ref={inputRef}
          className={`nl-form__input ${speech.interim ? 'nl-form__input--interim' : ''}`}
          type="text"
          value={display}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // The form may sit inside the editor's <form>; Enter parses here
            // instead of submitting the half-empty transaction.
            if (e.key === 'Enter') {
              e.preventDefault()
              void handleParse()
            }
          }}
          placeholder='e.g. "coffee at Starbucks 5.50 yesterday"'
          disabled={parse.isPending}
        />
        {speech.supported && !micHidden && (
          <button
            type="button"
            className={`nl-form__mic ${speech.listening ? 'nl-form__mic--listening' : ''}`}
            onClick={() => (speech.listening ? speech.stop() : speech.start())}
            aria-label={speech.listening ? 'Stop dictation' : 'Dictate'}
            title={speech.listening ? 'Listening — tap to stop' : 'Dictate'}
          >
            <Mic size={16} />
          </button>
        )}
        <button
          type="button"
          className="nl-form__parse"
          onClick={() => void handleParse()}
          disabled={!text.trim() || parse.isPending}
        >
          {parse.isPending ? 'Drafting…' : 'Draft it'}
        </button>
      </div>
      <p className="nl-form__hint">
        {speech.listening
          ? 'Listening — speak your transaction, then tap the mic to stop.'
          : "You'll confirm every detail before anything is saved."}
      </p>
    </div>
  )
}
