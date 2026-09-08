import { describe, expect, it } from 'vitest'
import { diagnoseGap, readViewportSnapshot, type ViewportSnapshot } from './useViewportDiagnostics'

const tokens = (safeTop: number) => ({
  '--safe-top': safeTop,
  '--safe-bottom': 34,
  '--vvh': 0,
  '--app-h': 0,
  '--nav-h': 48,
  '--kb': 0,
})

function fakeWindow(overrides: Partial<{ clientH: number; vvH: number; standalone: boolean }>) {
  const clientH = overrides.clientH ?? 873
  return {
    document: { documentElement: { clientHeight: clientH } },
    screen: { width: 430, height: 932 },
    innerHeight: clientH,
    outerHeight: clientH,
    visualViewport: { height: overrides.vvH ?? clientH, offsetTop: 0, scale: 1 },
    navigator: { standalone: overrides.standalone ?? true },
    matchMedia: (q: string) => ({
      matches: q.includes('standalone') && overrides.standalone !== false,
    }),
  } as unknown as Window
}

describe('readViewportSnapshot', () => {
  it('reports every raw number rounded to whole pixels', () => {
    const s = readViewportSnapshot(fakeWindow({}), tokens(59), 'abc123')
    expect(s).toMatchObject({
      displayMode: 'standalone',
      standalone: true,
      screenW: 430,
      screenH: 932,
      clientH: 873,
      vvH: 873,
      vvTop: 0,
      vvScale: 1,
      buildId: 'abc123',
    })
    expect(s.tokens['--safe-top']).toBe(59)
  })

  it('falls back to the layout viewport when visualViewport is absent', () => {
    const win = fakeWindow({})
    Object.assign(win, { visualViewport: null })
    const s = readViewportSnapshot(win, tokens(0), 'dev')
    expect(s.vvH).toBe(873)
    expect(s.vvScale).toBe(1)
  })
})

describe('diagnoseGap', () => {
  const snap = (over: Partial<ViewportSnapshot>): ViewportSnapshot => ({
    ...readViewportSnapshot(fakeWindow({}), tokens(59), 'dev'),
    ...over,
  })

  it('names the iOS standalone case: short by exactly the top inset', () => {
    // The 2026-09-08 screenshot: 932pt screen, 873pt viewport, 59pt inset.
    expect(diagnoseGap(snap({}))).toBe('status-bar-hidden')
  })

  it('says none once the layout viewport reaches the screen', () => {
    expect(diagnoseGap(snap({ clientH: 932 }))).toBe('none')
  })

  it('never diagnoses a browser tab, which is short by its chrome', () => {
    expect(diagnoseGap(snap({ standalone: false, clientH: 780 }))).toBe('none')
  })

  it('flags a shortfall that is not the inset for the ruler to explain', () => {
    expect(diagnoseGap(snap({ clientH: 850 }))).toBe('other')
  })
})
