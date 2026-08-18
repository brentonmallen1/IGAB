import { describe, expect, it } from 'vitest'
import { fitWithin, shouldDownscale } from './imageUpload'

describe('fitWithin', () => {
  it('leaves images already within the cap alone', () => {
    expect(fitWithin(1600, 1200, 2048)).toEqual({ width: 1600, height: 1200 })
  })

  it('scales the longest side down to the cap, preserving aspect', () => {
    // A typical iPhone photo, landscape.
    expect(fitWithin(4032, 3024, 2048)).toEqual({ width: 2048, height: 1536 })
  })

  it('handles portrait, where height is the longest side', () => {
    expect(fitWithin(3024, 4032, 2048)).toEqual({ width: 1536, height: 2048 })
  })

  it('keeps a very tall receipt scan readable rather than squashing it', () => {
    expect(fitWithin(1000, 8000, 2048)).toEqual({ width: 256, height: 2048 })
  })

  it('never returns zero or negative dimensions', () => {
    expect(fitWithin(0, 0, 2048)).toEqual({ width: 0, height: 0 })
    const r = fitWithin(4000, 1, 2048)
    expect(r.height).toBeGreaterThanOrEqual(0)
  })
})

describe('shouldDownscale', () => {
  function make(type: string, size: number): File {
    const f = new File([new Uint8Array(1)], 'receipt', { type })
    Object.defineProperty(f, 'size', { value: size })
    return f
  }

  it('shrinks a large photo', () => {
    expect(shouldDownscale(make('image/jpeg', 4 * 1024 * 1024))).toBe(true)
    expect(shouldDownscale(make('image/heic', 3 * 1024 * 1024))).toBe(true)
  })

  it('leaves PDFs alone — re-encoding would drop every page but the first', () => {
    expect(shouldDownscale(make('application/pdf', 4 * 1024 * 1024))).toBe(false)
  })

  it('leaves already-small images alone', () => {
    expect(shouldDownscale(make('image/jpeg', 100 * 1024))).toBe(false)
  })

  it('ignores non-images', () => {
    expect(shouldDownscale(make('text/plain', 4 * 1024 * 1024))).toBe(false)
  })
})
