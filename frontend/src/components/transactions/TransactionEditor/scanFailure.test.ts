/**
 * A scan that failed because no vision model is configured and a scan that
 * failed because the photo was unreadable produce the identical $0 stub. Only
 * one of them is fixable in Settings, so the banner has to tell them apart.
 */
import { describe, expect, it } from 'vitest'
import { isConfigFailure, scanFailureReason } from './scanFailure'

describe('scanFailureReason', () => {
  it('strips the exception class the worker prefixes onto job.error', () => {
    expect(
      scanFailureReason(
        "NonRetryableJobError: Model 'gemma4:31b' does not support vision — set a vision model in Settings → AI"
      )
    ).toBe("Model 'gemma4:31b' does not support vision — set a vision model in Settings → AI")
  })

  it('falls back to generic guidance when the job recorded no reason', () => {
    expect(scanFailureReason(null)).toMatch(/enter the details from the image/)
    expect(scanFailureReason(undefined)).toMatch(/enter the details from the image/)
    expect(scanFailureReason('')).toMatch(/enter the details from the image/)
  })

  it('leaves an already-clean message alone', () => {
    expect(scanFailureReason('Receipt image is missing')).toBe('Receipt image is missing')
  })
})

describe('isConfigFailure', () => {
  it('recognises the fixable causes', () => {
    expect(isConfigFailure("NonRetryableJobError: Model 'x' does not support vision")).toBe(true)
    expect(isConfigFailure('Ollama is not configured — set a host in Settings → AI')).toBe(true)
  })

  it('does not offer a Settings link for something Settings cannot fix', () => {
    // A bad photo is the user's problem to solve with a better photo.
    expect(
      isConfigFailure(
        "NonRetryableJobError: The image doesn't appear to be a receipt — created an empty transaction"
      )
    ).toBe(false)
    expect(isConfigFailure('Receipt image is missing')).toBe(false)
    expect(isConfigFailure(null)).toBe(false)
  })
})
