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
        "NonRetryableJobError: Model 'gemma4:31b' does not support vision — set a vision model in System → AI"
      )
    ).toBe("Model 'gemma4:31b' does not support vision — set a vision model in System → AI")
  })

  it('falls back to generic guidance when the job recorded no reason', () => {
    expect(scanFailureReason(null)).toMatch(/enter the details from the image/)
    expect(scanFailureReason(undefined)).toMatch(/enter the details from the image/)
    expect(scanFailureReason('')).toMatch(/enter the details from the image/)
  })

  it('strips any exception name an older job carries, not only …Error', () => {
    expect(scanFailureReason("ReplyNotJSON: The model's reply held no JSON object")).toBe(
      "The model's reply held no JSON object"
    )
  })

  it('reads a bare timeout from before the plain-language messages as the general guidance', () => {
    expect(scanFailureReason('ReadTimeout: ')).toMatch(/enter the details from the image/)
  })

  it('leaves a sentence that starts with an ordinary word and a colon alone', () => {
    expect(scanFailureReason('Note: the photo was blurry')).toBe('Note: the photo was blurry')
  })

  it('leaves an already-clean message alone', () => {
    expect(scanFailureReason('Receipt image is missing')).toBe('Receipt image is missing')
  })
})

describe('isConfigFailure', () => {
  it('recognises the fixable causes', () => {
    expect(isConfigFailure("NonRetryableJobError: Model 'x' does not support vision")).toBe(true)
    expect(isConfigFailure('Ollama is not configured — set a host in System → AI')).toBe(true)
  })

  it('still recognises a job recorded before the AI section moved pages', () => {
    expect(isConfigFailure('Pick a vision-capable model in Settings → AI.')).toBe(true)
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
