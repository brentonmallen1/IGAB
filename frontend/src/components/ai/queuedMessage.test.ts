import { describe, expect, it } from 'vitest'
import { queuedMessage } from './queuedMessage'

describe('queuedMessage', () => {
  it('keeps the words a scan has always used', () => {
    expect(queuedMessage('receipt', 1, false)).toBe(
      "Receipt queued — it'll show up in your transactions to review"
    )
    expect(queuedMessage('receipt', 3, true)).toBe(
      "3 receipts queued — they wait in AI Activity until they have an account, and aren't in your budget until then"
    )
  })

  it('says the same of a description', () => {
    expect(queuedMessage('description', 1, false)).toBe(
      "Description queued — it'll show up in your transactions to review"
    )
    expect(queuedMessage('description', 1, true)).toMatch(/waits in AI Activity/)
  })
})
