/**
 * Teardown guarantees for dictation: whatever ends a session — error, stop,
 * wedged browser session, tab hidden, unmount — the recognition object must
 * be aborted and detached. A capture left open against a dead session is the
 * failure mode these tests exist to prevent.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSpeechRecognition } from './useSpeechRecognition'

class FakeRecognition {
  static instances: FakeRecognition[] = []
  lang = ''
  interimResults = false
  continuous = false
  onresult: ((event: unknown) => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  started = false
  aborted = false
  stopped = false
  constructor() {
    FakeRecognition.instances.push(this)
  }
  start() {
    this.started = true
  }
  stop() {
    this.stopped = true
  }
  abort() {
    this.aborted = true
  }
}

function lastRecognition(): FakeRecognition {
  const rec = FakeRecognition.instances.at(-1)
  if (!rec) throw new Error('no recognition instance created')
  return rec
}

function setSecureContext(value: boolean) {
  Object.defineProperty(window, 'isSecureContext', { value, configurable: true })
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeRecognition.instances = []
  setSecureContext(true)
  ;(window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition = FakeRecognition
})

afterEach(() => {
  vi.useRealTimers()
  delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition
})

describe('useSpeechRecognition teardown guarantees', () => {
  it('starts a session and reports listening', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    expect(result.current.supported).toBe(true)
    act(() => result.current.start())
    expect(lastRecognition().started).toBe(true)
    expect(result.current.listening).toBe(true)
  })

  it('a service error aborts the capture and surfaces the code — without waiting for onend', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    const rec = lastRecognition()
    act(() => rec.onerror!({ error: 'network' }))
    expect(rec.aborted).toBe(true)
    expect(rec.onresult).toBeNull()
    expect(rec.onend).toBeNull()
    expect(result.current.listening).toBe(false)
    expect(result.current.error).toBe('network')
  })

  it('benign errors still kill the session, silently', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    const rec = lastRecognition()
    act(() => rec.onerror!({ error: 'no-speech' }))
    expect(rec.aborted).toBe(true)
    expect(result.current.listening).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('the watchdog force-kills a wedged session that stops emitting events', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    const rec = lastRecognition()
    act(() => {
      vi.advanceTimersByTime(46_000)
    })
    expect(rec.aborted).toBe(true)
    expect(result.current.listening).toBe(false)
  })

  it('stop() that never gets an onend is force-killed by the safety net', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    const rec = lastRecognition()
    act(() => result.current.stop())
    expect(rec.stopped).toBe(true)
    expect(rec.aborted).toBe(false)
    act(() => {
      vi.advanceTimersByTime(3_500)
    })
    expect(rec.aborted).toBe(true)
    expect(result.current.listening).toBe(false)
  })

  it('hiding the tab kills a live session', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    const rec = lastRecognition()
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    expect(rec.aborted).toBe(true)
    expect(result.current.listening).toBe(false)
  })

  it('unmount kills a live session', () => {
    const { result, unmount } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    const rec = lastRecognition()
    unmount()
    expect(rec.aborted).toBe(true)
  })

  it('restarting mid-session kills the old capture before opening a new one', () => {
    const { result } = renderHook(() => useSpeechRecognition())
    act(() => result.current.start())
    const first = lastRecognition()
    act(() => result.current.start())
    expect(FakeRecognition.instances).toHaveLength(2)
    expect(first.aborted).toBe(true)
    expect(lastRecognition().started).toBe(true)
  })

  it('insecure origins get no dictation at all — Chrome would open the mic and then refuse', () => {
    setSecureContext(false)
    const { result } = renderHook(() => useSpeechRecognition())
    expect(result.current.supported).toBe(false)
    act(() => result.current.start())
    expect(FakeRecognition.instances).toHaveLength(0)
    expect(result.current.listening).toBe(false)
  })
})
