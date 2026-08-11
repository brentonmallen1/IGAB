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

/**
 * On-device dictation via the browser's Web Speech API (Siri on iOS Safari,
 * Google on Android Chrome). The transcript is never auto-submitted — it
 * lands in an editable input and the user confirms before parsing.
 */
export function useSpeechRecognition() {
  const [supported] = useState(() => getSpeechRecognition() !== null)
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  useEffect(() => {
    return () => recognitionRef.current?.abort()
  }, [])

  const start = useCallback(() => {
    const Ctor = getSpeechRecognition()
    if (!Ctor || recognitionRef.current) return
    setError(null)
    setTranscript('')
    setInterim('')

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
      // 'no-speech' on a quick tap isn't worth surfacing; permission
      // problems are — the caller hides the mic for the session.
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(event.error)
      }
    }
    recognition.onend = () => {
      setListening(false)
      setInterim('')
      recognitionRef.current = null
    }

    recognitionRef.current = recognition
    setListening(true)
    try {
      recognition.start()
    } catch {
      setListening(false)
      recognitionRef.current = null
    }
  }, [])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  return { supported, listening, transcript, interim, error, start, stop, setTranscript }
}
