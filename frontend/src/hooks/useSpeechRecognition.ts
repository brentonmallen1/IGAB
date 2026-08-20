import { useCallback, useEffect, useRef, useState } from 'react'

/* Web Speech API typings — not in TS's dom lib. Chrome/Safari expose the
 * prefixed constructor; Firefox has neither (we feature-detect and hide). */
interface SpeechRecognitionResultLike {
  isFinal: boolean
  0: { transcript: string }
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<SpeechRecognitionResultLike>
}

interface SpeechRecognitionErrorEventLike {
  error: string
}

interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

/* Chrome's recognizer is Google-hosted and refuses insecure origins — but
 * only AFTER it has opened the microphone, leaving the capture indicator lit
 * against a dead session. On http:// the feature is structurally broken in
 * every configuration we care about, so don't offer the mic at all. */
function speechAvailable(): boolean {
  return getSpeechRecognition() !== null && window.isSecureContext
}

/** A session may not last longer than this. Sessions are single-utterance
 * (continuous=false) and end themselves in seconds — the watchdog only fires
 * when the browser's session is wedged and has stopped emitting events. */
const SESSION_MAX_MS = 45_000

/**
 * On-device dictation via the browser's Web Speech API (Siri on iOS Safari,
 * Google on Android Chrome). The transcript is never auto-submitted — it
 * lands in an editable input and the user confirms before parsing.
 *
 * Every session runs inside guaranteed-teardown semantics: whatever ends it —
 * user stop, error, wedged session (watchdog), tab hidden, unmount — the
 * recognition object is detached and aborted, and our state resets. Cleanup
 * never depends on the browser firing `onend`, because in the failure mode
 * that matters most (service refusal mid-capture) Chrome doesn't.
 */
export function useSpeechRecognition() {
  const [supported] = useState(speechAvailable)
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const watchdogRef = useRef<number | null>(null)

  // Idempotent hard-kill: detach handlers first so nothing the dying session
  // still emits can touch state, then abort AND stop (belt and braces — a
  // wedged session has ignored one of them before).
  const teardown = useCallback(() => {
    if (watchdogRef.current !== null) {
      window.clearTimeout(watchdogRef.current)
      watchdogRef.current = null
    }
    const recognition = recognitionRef.current
    recognitionRef.current = null
    if (recognition) {
      recognition.onresult = null
      recognition.onerror = null
      recognition.onend = null
      try {
        recognition.abort()
      } catch {
        /* already dead */
      }
      try {
        recognition.stop()
      } catch {
        /* already dead */
      }
    }
    setListening(false)
    setInterim('')
  }, [])

  // A backgrounded tab must not keep capturing — kill any live session the
  // moment the page hides, and always on unmount.
  useEffect(() => {
    function onHidden() {
      if (document.visibilityState === 'hidden') teardown()
    }
    document.addEventListener('visibilitychange', onHidden)
    return () => {
      document.removeEventListener('visibilitychange', onHidden)
      teardown()
    }
  }, [teardown])

  const start = useCallback(() => {
    const Ctor = getSpeechRecognition()
    if (!Ctor || !window.isSecureContext) return
    // A stale session (shouldn't exist, but never trust it) dies before a new
    // one starts — at most one capture, ever.
    teardown()
    setError(null)
    setTranscript('')

    const recognition = new Ctor()
    recognition.lang = navigator.language || 'en-US'
    recognition.interimResults = true
    recognition.continuous = false

    recognition.onresult = (event) => {
      let finalText = ''
      let interimText = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) finalText += result[0].transcript
        else interimText += result[0].transcript
      }
      if (finalText) setTranscript((prev) => (prev + ' ' + finalText).trim())
      setInterim(interimText)
    }
    recognition.onerror = (event) => {
      // 'no-speech' on a quick tap isn't worth surfacing; permission and
      // service problems are — the caller maps the code to specific copy.
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(event.error)
      }
      // ANY error ends the session, benign or not. Cleanup here, not in
      // onend — Chrome doesn't reliably fire onend after a service error.
      teardown()
    }
    recognition.onend = () => teardown()

    recognitionRef.current = recognition
    watchdogRef.current = window.setTimeout(teardown, SESSION_MAX_MS)
    setListening(true)
    try {
      recognition.start()
    } catch {
      teardown()
    }
  }, [teardown])

  const stop = useCallback(() => {
    // stop() (not abort) lets in-flight audio finalize into a result — but
    // arm the safety net: if no onend arrives shortly, teardown anyway.
    const recognition = recognitionRef.current
    if (!recognition) return
    try {
      recognition.stop()
    } catch {
      teardown()
      return
    }
    if (watchdogRef.current !== null) window.clearTimeout(watchdogRef.current)
    watchdogRef.current = window.setTimeout(teardown, 3_000)
  }, [teardown])

  return { supported, listening, transcript, interim, error, start, stop, setTranscript }
}
