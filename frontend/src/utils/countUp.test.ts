import { describe, expect, it } from 'vitest'
import { COUNT_UP_MS, countUpValue } from './countUp'

describe('countUpValue', () => {
  it('starts on the old figure', () => {
    expect(countUpValue(240, 198, 0)).toBe(240)
  })

  it('treats a clock that has not started as the start', () => {
    expect(countUpValue(240, 198, -16)).toBe(240)
  })

  it('stops exactly on the new figure', () => {
    expect(countUpValue(240, 198, COUNT_UP_MS)).toBe(198)
  })

  it('stays on the new figure once the count is over', () => {
    expect(countUpValue(240, 198, COUNT_UP_MS * 3)).toBe(198)
  })

  it("returns the server's figure itself on the last frame, not a rebuilt one", () => {
    // 0.1 + 0.2 is not 0.3 in float; the end of the count is not arithmetic.
    const served = 0.1 + 0.2
    expect(countUpValue(10, served, COUNT_UP_MS)).toBe(served)
  })

  it('is the new figure at once when there is no time to count in', () => {
    expect(countUpValue(240, 198, 0, 0)).toBe(198)
  })

  it('moves between the two, eased so most of the change comes early', () => {
    const halfway = countUpValue(0, 100, COUNT_UP_MS / 2)
    expect(halfway).toBeGreaterThan(50)
    expect(halfway).toBeLessThan(100)
  })

  it('prints whole cents on every frame', () => {
    for (let t = 0; t <= COUNT_UP_MS; t += 7) {
      const v = countUpValue(240.01, 198.37, t)
      expect(Math.round(v * 100) / 100).toBe(v)
    }
  })

  it('rounds a frame to the nearest cent', () => {
    // 1 cent to 2 cents: the eased midpoint is 0.875 of the way, 1.875 cents.
    expect(countUpValue(0.01, 0.02, COUNT_UP_MS / 2)).toBe(0.02)
    // 1 to 3 cents a quarter in: 0.578 of 2 cents on top of 1 is 2.156 cents.
    expect(countUpValue(0.01, 0.03, COUNT_UP_MS / 4)).toBe(0.02)
    // 0 to 1 cent a twentieth in: 0.143 of a cent rounds down to nothing.
    expect(countUpValue(0, 0.01, COUNT_UP_MS / 20)).toBe(0)
  })

  it('crosses zero into an overspend, never skipping the sign change', () => {
    const frames = Array.from({ length: 61 }, (_, i) =>
      countUpValue(20, -22, (COUNT_UP_MS * i) / 60)
    )
    expect(frames[0]).toBe(20)
    expect(frames.at(-1)).toBe(-22)
    expect(frames.some((v) => v > 0)).toBe(true)
    expect(frames.some((v) => v < 0)).toBe(true)
    // Monotonic: a count down never ticks back up on its way through zero.
    for (let i = 1; i < frames.length; i++) expect(frames[i]).toBeLessThanOrEqual(frames[i - 1])
  })

  it('counts up out of an overspend too', () => {
    expect(countUpValue(-12.5, 30, 0)).toBe(-12.5)
    expect(countUpValue(-12.5, 30, COUNT_UP_MS)).toBe(30)
  })

  it('holds still when nothing changed', () => {
    expect(countUpValue(0, 0, COUNT_UP_MS / 2)).toBe(0)
    expect(countUpValue(45.5, 45.5, COUNT_UP_MS / 3)).toBe(45.5)
  })
})
