import { describe, expect, it } from 'vitest'
import {
  diagnoseGap,
  readViewportSnapshot,
  shellShortfall,
  type ViewportSnapshot,
} from './useViewportDiagnostics'

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

  // Every case is the shell against the WEB VIEW. The screen is context.
  it('says none when the shell covers the layout viewport', () => {
    // The opaque status bar: a 932pt screen, an 873pt web view below the bar,
    // and a shell that fills it. `screen − layout` is 59 and healthy.
    expect(diagnoseGap(snap({ clientH: 873, tokens: { ...tokens(0), '--app-h': 873 } }))).toBe(
      'none'
    )
  })

  it('says short when the shell stops above the web view, which is the band', () => {
    // The shipped bug, in its own arithmetic: the nav ended at 873 and the
    // strip below it was bare.
    const s = snap({ clientH: 932, tokens: { ...tokens(0), '--app-h': 873 } })
    expect(diagnoseGap(s)).toBe('short')
    expect(shellShortfall(s)).toBe(59)
  })

  it('tolerates a pixel of rounding', () => {
    expect(diagnoseGap(snap({ clientH: 874, tokens: { ...tokens(0), '--app-h': 873 } }))).toBe(
      'none'
    )
  })

  it('never calls a browser tab short: it is the chrome that takes the height, not the shell', () => {
    // 780pt of web view under Safari's toolbars, filled to the last pixel.
    expect(
      diagnoseGap(
        snap({ standalone: false, clientH: 780, tokens: { ...tokens(0), '--app-h': 780 } })
      )
    ).toBe('none')
  })
})
