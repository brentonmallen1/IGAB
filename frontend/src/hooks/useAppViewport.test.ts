import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { computeViewportMetrics } from './useAppViewport'

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

describe('--app-h reads the measurement rather than rebuilding it', () => {
  // The band under the bottom nav in the installed iOS PWA, reported four
  // times. `--app-h` was `calc(100dvh - var(--kb) - var(--vv-top))` — a
  // reconstruction of the number this hook already measures, and one that is
  // only correct while 100dvh equals the visible height.
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

describe('the status bar is opaque, which is what makes those heights true', () => {
  // The pair is the contract. Reading a measured height is only correct while
  // the web view begins BELOW the status bar; under `black-translucent` the
  // view starts at the physical top of the screen and every height the
  // platform reports — 100dvh, innerHeight, clientHeight and
  // visualViewport.height alike — is short by env(safe-area-inset-top). The
  // fixed shell is then clipped at the layout viewport and the inset-sized
  // strip below it cannot be painted from inside the page: on a 932pt screen
  // the nav was cut through its icons at 873pt. Two fixes computed 59
  // correctly and neither could draw it.
  //
  // jsdom has no safe-area insets and no web view, so nothing but the source
  // can hold this.
  const html = readFileSync(resolve(__dirname, '../../index.html'), 'utf8')
  const style = html.match(
    /<meta\s+name="apple-mobile-web-app-status-bar-style"\s+content="([^"]+)"/
  )?.[1]

  it('is declared', () => {
    expect(style).toBeDefined()
  })

  it('is not translucent', () => {
    expect(style).not.toBe('black-translucent')
  })

  it('is default, so iOS paints the bar from theme-color', () => {
    // `black` is the fallback if a device ignores theme-color; changing to it
    // is a deliberate decision, not a drive-by edit.
    expect(style).toBe('default')
  })

  it('still covers the viewport, which is where the bottom inset comes from', () => {
    expect(html).toMatch(/viewport-fit=cover/)
  })
})
