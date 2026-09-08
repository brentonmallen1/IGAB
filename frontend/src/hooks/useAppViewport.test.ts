import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { computeViewportMetrics, standaloneStatusBarGap } from './useAppViewport'

/**
 * The viewport contract is the foundation every fixed-position element in the
 * app resolves against, so it is tested against the real hardware situations
 * rather than round numbers.
 */
describe('computeViewportMetrics', () => {
  it('reports no insets when nothing occludes the viewport', () => {
    expect(computeViewportMetrics(844, 844, 0)).toEqual({
      height: 844,
      offsetTop: 0,
      bottomInset: 0,
    })
  })

  it('treats a Safari toolbar as a bottom inset', () => {
    // A Safari tab hides ~64px behind its toolbar with no keyboard at all —
    // the case the old `innerHeight - 50` heuristic misread as a keyboard.
    expect(computeViewportMetrics(844, 780, 0)).toEqual({
      height: 780,
      offsetTop: 0,
      bottomInset: 64,
    })
  })

  it('measures an iOS keyboard that shrinks without offsetting', () => {
    expect(computeViewportMetrics(844, 508, 0)).toEqual({
      height: 508,
      offsetTop: 0,
      bottomInset: 336,
    })
  })

  it('measures an iOS keyboard that also scrolled the visual viewport', () => {
    // The case that fires `scroll` and no `resize`, and that the previous
    // implementation was structurally blind to.
    expect(computeViewportMetrics(844, 508, 120)).toEqual({
      height: 508,
      offsetTop: 120,
      bottomInset: 216,
    })
  })

  it('yields a zero inset under interactive-widget=resizes-content', () => {
    // Android shrinks the LAYOUT viewport, so the keyboard is already gone
    // from the geometry. Subtracting again would double-count it.
    expect(computeViewportMetrics(508, 508, 0)).toEqual({
      height: 508,
      offsetTop: 0,
      bottomInset: 0,
    })
  })

  it('reports a hardware-keyboard accessory bar as a small inset', () => {
    // 44px — below KEYBOARD_MIN_PX, so the caller leaves --kb at 0 while the
    // geometry still accounts for the occlusion.
    expect(computeViewportMetrics(844, 800, 0)).toEqual({
      height: 800,
      offsetTop: 0,
      bottomInset: 44,
    })
  })

  it('never produces negative insets from sub-pixel measurements', () => {
    const m = computeViewportMetrics(844, 844.3, -0.2)
    expect(m.offsetTop).toBe(0)
    expect(m.bottomInset).toBe(0)
  })

  it('rounds to whole pixels so CSS never receives fractional values', () => {
    const m = computeViewportMetrics(844.6, 507.4, 120.5)
    expect(Number.isInteger(m.height)).toBe(true)
    expect(Number.isInteger(m.offsetTop)).toBe(true)
    expect(Number.isInteger(m.bottomInset)).toBe(true)
  })
})

describe('standaloneStatusBarGap', () => {
  // The user's screenshot, 2026-09-08: a 932pt screen, 59pt top inset, and a
  // 59pt band of bare page background under the bottom nav — AFTER --app-h
  // had been switched to visualViewport.height. The measured height is short
  // by the inset too, so the correction has to come from the arithmetic.
  it('is the top inset in an installed iOS PWA whose viewport is short by exactly that', () => {
    expect(standaloneStatusBarGap(true, 932, 873, 59)).toBe(59)
  })

  it('tolerates a pixel of rounding between the three measurements', () => {
    expect(standaloneStatusBarGap(true, 932, 874, 59)).toBe(59)
    expect(standaloneStatusBarGap(true, 932, 872, 59)).toBe(59)
  })

  it('is zero on desktop, where the window is not the screen', () => {
    expect(standaloneStatusBarGap(false, 1440, 900, 0)).toBe(0)
    // Even an installed desktop PWA: no inset, nothing to correct.
    expect(standaloneStatusBarGap(true, 1440, 900, 0)).toBe(0)
  })

  it('is zero in a Safari tab, which is short by its toolbars, not the inset', () => {
    expect(standaloneStatusBarGap(false, 932, 780, 59)).toBe(0)
    // Same numbers with standalone wrongly true: the equality still fails.
    expect(standaloneStatusBarGap(true, 932, 780, 59)).toBe(0)
  })

  it('is zero in landscape, where the inset is zero', () => {
    // screen.height stays the portrait value on iOS; the equality cannot hold.
    expect(standaloneStatusBarGap(true, 932, 430, 0)).toBe(0)
  })

  it('is zero on Android standalone, where the status bar is outside the web view', () => {
    // Layout viewport short by a 24px status bar, but the inset reports 0.
    expect(standaloneStatusBarGap(true, 915, 891, 0)).toBe(0)
  })

  it('is zero while the keyboard is up, even in standalone', () => {
    // clientHeight does not shrink for the keyboard on iOS, so the equality
    // holds regardless; this pins that the correction is independent of it.
    expect(standaloneStatusBarGap(true, 932, 873, 59)).toBe(59)
    expect(computeViewportMetrics(873, 508, 0, 59)).toEqual({
      height: 567,
      offsetTop: 0,
      bottomInset: 365,
    })
  })
})

describe('computeViewportMetrics with a hidden top inset', () => {
  it('adds the inset to the height and nothing else', () => {
    expect(computeViewportMetrics(873, 873, 0, 59)).toEqual({
      height: 932,
      offsetTop: 0,
      bottomInset: 0,
    })
  })

  it('defaults the inset to zero so every existing caller is unchanged', () => {
    expect(computeViewportMetrics(844, 844, 0)).toEqual(computeViewportMetrics(844, 844, 0, 0))
  })
})

// --- Integration: the effect that publishes the metrics to <html> ---

class FakeVisualViewport extends EventTarget {
  height = 844
  offsetTop = 0
  scale = 1
  emit(type: 'resize' | 'scroll') {
    this.dispatchEvent(new Event(type))
  }
}

const root = () => document.documentElement
const prop = (name: string) => root().style.getPropertyValue(name)

async function mountHook() {
  const { renderHook } = await import('@testing-library/react')
  const { useAppViewport } = await import('./useAppViewport')
  return renderHook(() => useAppViewport())
}

describe('useAppViewport', () => {
  let vv: FakeVisualViewport
  let scrollTo: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.useFakeTimers()
    vv = new FakeVisualViewport()
    Object.defineProperty(window, 'visualViewport', { value: vv, configurable: true })
    Object.defineProperty(root(), 'clientHeight', { value: 844, configurable: true })
    // Run rAF callbacks synchronously so assertions don't race the scheduler.
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', () => {})
    scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    root().removeAttribute('data-keyboard')
  })

  function focusEditable() {
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    return input
  }

  it('publishes resting geometry on mount', async () => {
    await mountHook()
    expect(prop('--vvh')).toBe('844px')
    expect(prop('--vv-top')).toBe('0px')
    expect(prop('--vv-bottom')).toBe('0px')
    expect(prop('--kb')).toBe('0px')
  })

  it('responds to scroll as well as resize', async () => {
    await mountHook()
    // iOS offsets the visual viewport WITHOUT resizing it: scroll only.
    vv.offsetTop = 120
    vv.height = 508
    vv.emit('scroll')
    expect(prop('--vv-top')).toBe('120px')
    expect(prop('--vv-bottom')).toBe('216px')
  })

  it('freezes while pinch-zoomed, when measurements mean nothing for layout', async () => {
    await mountHook()
    vv.scale = 1.5
    vv.height = 400
    vv.emit('resize')
    expect(prop('--vvh')).toBe('844px')
  })

  it('sets --kb only when an editable is focused AND the inset is keyboard-sized', async () => {
    await mountHook()

    // Big inset, nothing focused (a UA toolbar) — geometry updates, --kb doesn't.
    vv.height = 508
    vv.emit('resize')
    expect(prop('--vv-bottom')).toBe('336px')
    expect(prop('--kb')).toBe('0px')
    expect(root().hasAttribute('data-keyboard')).toBe(false)

    // Editable focused, same inset — now it's a keyboard.
    focusEditable()
    vv.emit('resize')
    expect(prop('--kb')).toBe('336px')
    expect(root().getAttribute('data-keyboard')).toBe('open')
  })

  it('ignores an accessory-bar-sized inset even with a field focused', async () => {
    await mountHook()
    focusEditable()
    vv.height = 800 // 44px inset — below the keyboard threshold
    vv.emit('resize')
    expect(prop('--kb')).toBe('0px')
    expect(root().hasAttribute('data-keyboard')).toBe(false)
  })

  it('does not flap when focus moves between fields', async () => {
    await mountHook()
    const first = focusEditable()
    vv.height = 508
    vv.emit('resize')
    expect(root().getAttribute('data-keyboard')).toBe('open')

    // Tabbing to the next field: focusout then focusin, keyboard never lowers.
    first.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    vi.advanceTimersByTime(50)
    focusEditable()
    vi.advanceTimersByTime(200)

    expect(root().getAttribute('data-keyboard')).toBe('open')
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('forces one relayout when the keyboard closes', async () => {
    await mountHook()
    const input = focusEditable()
    vv.height = 508
    vv.emit('resize')
    expect(scrollTo).not.toHaveBeenCalled()

    // Keyboard dismissed: field blurs and the viewport comes back.
    input.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    vv.height = 844
    vi.advanceTimersByTime(200)

    expect(prop('--kb')).toBe('0px')
    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })

  it('falls back to the layout viewport when visualViewport is unavailable', async () => {
    Object.defineProperty(window, 'visualViewport', { value: undefined, configurable: true })
    await mountHook()
    expect(prop('--vvh')).toBe('844px')
    expect(prop('--vv-bottom')).toBe('0px')
  })

  it('removes every property and attribute on teardown', async () => {
    const { unmount } = await mountHook()
    focusEditable()
    vv.height = 508
    vv.emit('resize')
    expect(root().hasAttribute('data-keyboard')).toBe(true)

    unmount()
    for (const name of ['--vvh', '--vv-top', '--vv-bottom', '--kb']) {
      expect(prop(name)).toBe('')
    }
    expect(root().hasAttribute('data-keyboard')).toBe(false)
  })
})

describe('useAppViewport in an installed iOS PWA', () => {
  let vv: FakeVisualViewport

  beforeEach(() => {
    vv = new FakeVisualViewport()
    vv.height = 873
    Object.defineProperty(window, 'visualViewport', { value: vv, configurable: true })
    Object.defineProperty(root(), 'clientHeight', { value: 873, configurable: true })
    Object.defineProperty(window.screen, 'height', { value: 932, configurable: true })
    Object.defineProperty(window.navigator, 'standalone', { value: true, configurable: true })
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', () => {})
    vi.stubGlobal('scrollTo', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    Object.defineProperty(window.navigator, 'standalone', { value: undefined, configurable: true })
  })

  it('publishes the full screen height once the safe-top probe measures the inset', async () => {
    await mountHook()
    // jsdom lays nothing out, so the probe reads 0 until told otherwise: the
    // first write leaves --vvh at the reported 873px…
    expect(prop('--vvh')).toBe('873px')
    const probe = document.querySelector('[data-viewport-probe="safe-top"]') as HTMLElement
    expect(probe).not.toBeNull()
    Object.defineProperty(probe, 'offsetHeight', { value: 59, configurable: true })
    // …and the next measurement folds the 59px the platform paints but never reports.
    vv.emit('resize')
    expect(prop('--vvh')).toBe('932px')
    expect(prop('--vv-bottom')).toBe('0px')
  })

  it('removes the probe on unmount', async () => {
    const { unmount } = await mountHook()
    expect(document.querySelector('[data-viewport-probe]')).not.toBeNull()
    unmount()
    expect(document.querySelector('[data-viewport-probe]')).toBeNull()
  })
})

describe('--app-h reads the measurement rather than rebuilding it', () => {
  // The band under the bottom nav in the installed iOS PWA, reported three
  // times. `--app-h` was `calc(100dvh - var(--kb) - var(--vv-top))` — a
  // reconstruction of the number this hook already measures, and one that is
  // only correct while 100dvh equals the visible height. With
  // viewport-fit=cover plus black-translucent it does not: the web view's
  // origin is the physical top of the screen (the header really does paint
  // under the status bar) while 100dvh comes back short by exactly
  // env(safe-area-inset-top) — 59pt of bare page background below the nav on
  // a 932pt screen.
  //
  // Read as source because the failure is invisible to jsdom: it has no
  // safe-area insets, so every reconstruction agrees there and disagrees only
  // on hardware.
  const base = readFileSync(resolve(__dirname, '../themes/base.css'), 'utf8')
  const declaration = base.match(/^\s*--app-h:\s*(.+);$/m)?.[1] ?? ''

  it('is defined', () => {
    expect(declaration).not.toBe('')
  })

  it('is the measured visible height', () => {
    expect(declaration).toBe('var(--vvh)')
  })

  it('contains no viewport-unit arithmetic', () => {
    // --vvh's own fallback is 100dvh, which is right: it is what desktop and
    // the first paint before the effect runs see. A dvh term in --app-h
    // itself is the bug.
    // A length, not the tail of `--vvh`: `100dvh`, `100vh`, `100svh`.
    expect(declaration).not.toMatch(/\d\s*[dsl]?vh/)
  })
})
