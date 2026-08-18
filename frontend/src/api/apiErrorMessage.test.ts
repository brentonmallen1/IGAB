import { describe, expect, it } from 'vitest'
import { apiErrorMessage } from './client'

describe('apiErrorMessage', () => {
  const err = (detail: unknown) => ({ response: { data: { detail } } })

  it('reads the usual string detail', () => {
    expect(apiErrorMessage(err('File too large (max 20MB)'), 'fallback')).toBe(
      'File too large (max 20MB)'
    )
  })

  it('reads the message out of a structured detail', () => {
    // The duplicate-receipt 409 carries the existing transaction alongside the
    // message; reading `detail` blindly would render "[object Object]".
    expect(
      apiErrorMessage(
        err({ message: "You've already added this receipt", transaction_id: 'abc' }),
        'fallback'
      )
    ).toBe("You've already added this receipt")
  })

  it('falls back for an object with no message', () => {
    expect(apiErrorMessage(err({ transaction_id: 'abc' }), 'fallback')).toBe('fallback')
  })

  it('falls back for network errors with no response at all', () => {
    expect(apiErrorMessage(new Error('Network Error'), 'fallback')).toBe('fallback')
    expect(apiErrorMessage(undefined, 'fallback')).toBe('fallback')
    expect(apiErrorMessage(err(undefined), 'fallback')).toBe('fallback')
  })

  it('falls back on an empty string rather than showing a blank toast', () => {
    expect(apiErrorMessage(err(''), 'fallback')).toBe('fallback')
  })

  it('falls back for a validation-array detail rather than stringifying it', () => {
    expect(apiErrorMessage(err([{ loc: ['body'], msg: 'bad' }]), 'fallback')).toBe('fallback')
  })
})
