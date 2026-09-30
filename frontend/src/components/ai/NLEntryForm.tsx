import { useEffect, useRef, useState } from 'react'
import { Mic, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAIStatus } from '../../api/ai'
import { useSubmitDescription } from '../../api/aiJobs'
import { apiErrorMessage } from '../../api/client'
import { useSpeechRecognition } from '../../hooks/useSpeechRecognition'
import { queuedMessage, WAITS_FOR_AN_ACCOUNT } from './queuedMessage'
import './NLEntryForm.css'
import { sectionHref } from '../../pages/SettingsPage/settingsSections'

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
  /** Where the transaction goes; null and it waits in AI Activity until a
   *  person chooses. */
  accountId: string | null
  /** The words were handed off — the host closes. */
  onQueued: () => void
  /** Close the host surface before following a link (Settings). */
  onNavigate?: () => void
  autoFocus?: boolean
}

/**
 * The natural-language entry form: type or dictate "coffee starbucks 5.50
 * yesterday" and send it. Queued like a scanned receipt — nobody waits on
 * the model at a checkout — and the row turns up in the register to review.
 * Shared by the editor's "Describe it" tab and the mobile quick-entry sheet.
 */
export function NLEntryForm({
  budgetId,
  accountId,
  onQueued,
  onNavigate,
  autoFocus = true,
}: Props) {
  const aiStatus = useAIStatus()
  const submit = useSubmitDescription(budgetId)
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

  async function handleSend() {
    const trimmed = text.trim()
    if (!trimmed || submit.isPending) return
    if (speech.listening) speech.stop()
    try {
      await submit.mutateAsync({ text: trimmed, accountId })
      toast.success(queuedMessage('description', 1, !accountId), { duration: 6000 })
      onQueued()
    } catch (err: unknown) {
      // Nothing was queued: the words stay in the box to send again.
      toast.error(apiErrorMessage(err, "Couldn't send that — try again"))
    }
  }

  // Configured is enough: the words are queued and the worker retries, so a
  // model that is down right now must not stop anyone handing them off.
  if (aiStatus.data && !aiStatus.data.enabled) {
    return (
      <div className="nl-form__unavailable">
        <Sparkles size={20} />
        <p>Describing a transaction requires a configured Ollama server.</p>
        <Link
          to={sectionHref({ id: 'ai', page: 'system' })}
          className="nl-form__link"
          onClick={onNavigate}
        >
          Configure AI in System settings
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
          enterKeyHint="send"
          value={display}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // The form may sit inside the editor's <form>; Enter parses here
            // instead of submitting the half-empty transaction.
            if (e.key === 'Enter') {
              e.preventDefault()
              void handleSend()
            }
          }}
          placeholder='e.g. "coffee at Starbucks 5.50 yesterday"'
          disabled={submit.isPending}
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
          onClick={() => void handleSend()}
          disabled={!text.trim() || submit.isPending}
        >
          {submit.isPending ? 'Sending…' : 'Send'}
        </button>
      </div>
      <p className="nl-form__hint">
        {speech.listening
          ? 'Listening — speak your transaction, then tap the mic to stop.'
          : accountId
            ? "It's read in the background and turns up in your transactions to review."
            : WAITS_FOR_AN_ACCOUNT}
      </p>
    </div>
  )
}
