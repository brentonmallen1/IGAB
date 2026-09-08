import { useEffect } from 'react'

/**
 * Bottom inset that must be exceeded before we call the keyboard "open".
 *
 * iOS's form-accessory bar is ~44px and Safari's bottom toolbar ~50px; every
 * shipping software keyboard is well over 200px. Only the discretionary
 * `data-keyboard` signal uses this threshold — layout geometry never does, so
 * a wrong guess here is cosmetic rather than a broken screen.
 */
const KEYBOARD_MIN_PX = 120

/**
 * focusout fires before the next element focuses, so document.activeElement is
 * <body> mid-flight. Deferring the clear by a frame or two means field-to-field
 * tabbing — which never lowers the keyboard — doesn't flap data-keyboard.
 */
const BLUR_SETTLE_MS = 120

const EDITABLE =
  'input:not([readonly]):not([type=checkbox]):not([type=radio]):not([type=button])' +
  ':not([type=submit]):not([type=reset]):not([type=file]),' +
  'textarea:not([readonly]),select,[contenteditable]:not([contenteditable="false"])'

export interface ViewportMetrics {
  /** Height the app shell must fill, in CSS px: the visible height plus any
   *  region the platform paints but does not report (see standaloneStatusBarGap). */
  height: number
  /** Visual viewport's top edge, measured inside the layout viewport. */
  offsetTop: number
  /** Layout-viewport height hidden below the visible region (keyboard + UA chrome). */
  bottomInset: number
}

/**
 * The whole viewport contract, as a pure function so it can be tested
 * exhaustively without a browser.
 *
 * The question deliberately being answered is NOT "is the keyboard open" but
 * "how much of the layout viewport is currently not visible" — because a
 * `position: fixed` box is anchored to the layout viewport and is hidden by
 * the keyboard and by browser chrome identically. That question has an exact
 * answer and needs no heuristic.
 *
 * @param layoutHeight  documentElement.clientHeight — the ICB for position:fixed
 * @param visualHeight  visualViewport.height
 * @param visualOffsetTop visualViewport.offsetTop
 * @param hiddenTopInset  height the web view paints beyond every reported
 *   viewport — 0 everywhere except the standalone iOS case below
 */
export function computeViewportMetrics(
  layoutHeight: number,
  visualHeight: number,
  visualOffsetTop: number,
  hiddenTopInset = 0
): ViewportMetrics {
  return {
    height: Math.round(visualHeight + hiddenTopInset),
    offsetTop: Math.max(0, Math.round(visualOffsetTop)),
    bottomInset: Math.max(0, Math.round(layoutHeight - visualHeight - visualOffsetTop)),
  }
}

/**
 * The band under the bottom nav in the installed iOS PWA.
 *
 * With viewport-fit=cover and a black-translucent status bar, the web view
 * paints the full screen — the header genuinely runs under the status bar —
 * but every height the platform reports (100dvh, innerHeight,
 * documentElement.clientHeight AND visualViewport.height) comes back short by
 * exactly env(safe-area-inset-top). Sizing the shell to any of them leaves a
 * bare band of that height at the bottom. Measured off a screenshot of a
 * 932pt screen with a 59pt inset: shell bottom at 873pt, band 59pt.
 *
 * Gated on the arithmetic rather than on a platform sniff: the correction is
 * applied only when the layout viewport is short of the physical screen by
 * the top inset to within a pixel. A Safari tab (short by its toolbars, not
 * the inset), Android standalone (inset 0), landscape (inset 0), desktop
 * (screen ≠ window) and jsdom all compute 0 and are untouched.
 *
 * @param standalone  display-mode: standalone or navigator.standalone
 * @param screenHeight  window.screen.height (portrait-fixed on iOS)
 * @param layoutHeight  documentElement.clientHeight
 * @param safeTop  env(safe-area-inset-top), measured off a probe element
 */
export function standaloneStatusBarGap(
  standalone: boolean,
  screenHeight: number,
  layoutHeight: number,
  safeTop: number
): number {
  if (!standalone || safeTop <= 0) return 0
  return Math.abs(screenHeight - layoutHeight - safeTop) <= 1 ? Math.round(safeTop) : 0
}

/** True in an installed PWA on iOS (navigator.standalone) or anywhere else
 *  that honours the display-mode media feature. */
export function isStandaloneDisplay(win: Window = window): boolean {
  const nav = win.navigator as Navigator & { standalone?: boolean }
  if (nav.standalone === true) return true
  return typeof win.matchMedia === 'function'
    ? win.matchMedia('(display-mode: standalone)').matches
    : false
}

/**
 * A zero-width fixed element whose height is the top safe-area inset — the
 * only way to read env() as a number. Reads the alias rather than env()
 * itself so base.css stays the single place that types the env() name.
 */
export function mountSafeTopProbe(doc: Document): HTMLElement {
  const el = doc.createElement('div')
  el.setAttribute('data-viewport-probe', 'safe-top')
  el.setAttribute('aria-hidden', 'true')
  Object.assign(el.style, {
    position: 'fixed',
    top: '0',
    left: '0',
    width: '0',
    height: 'var(--safe-top)',
    visibility: 'hidden',
    pointerEvents: 'none',
  })
  doc.body.appendChild(el)
  return el
}

/**
 * Mounted exactly once at the app root. Publishes live visual-viewport
 * geometry as custom properties on <html> so CSS — not React — owns every
 * layout decision that depends on it.
 *
 * Why this exists: `position: fixed` anchors to the LAYOUT viewport. When iOS
 * raises the keyboard it shrinks the visual viewport and may scroll it inside
 * the unchanged layout viewport, so every fixed element (bottom sheet, bottom
 * nav, modal) ends up anchored to an edge that is no longer on screen. The
 * sheet slides out of view and the nav stops covering the page's bottom
 * padding, leaving a bare band. --vv-top / --vv-bottom cancel both exactly.
 *
 * Platform note: `interactive-widget=resizes-content` (set in index.html) is
 * honoured by Chrome, which shrinks the layout viewport so bottomInset
 * computes to 0 — and ignored by Safari, where it computes to the keyboard
 * height. The same expression is correct on both; there is no branch.
 */
export function useAppViewport() {
  useEffect(() => {
    const root = document.documentElement
    const vv = window.visualViewport
    const safeTopProbe = mountSafeTopProbe(document)
    let frame = 0
    // Separate from `frame` because `frame = requestAnimationFrame(cb)` assigns
    // AFTER cb runs if the callback is invoked synchronously — which would
    // leave a stale handle in `frame` and wedge every later schedule().
    let scheduled = false
    let editableFocused = false
    let blurTimer = 0
    let lastKeyboard = 0

    const write = () => {
      // Pinch-zoom makes every measurement meaningless for layout (the visual
      // viewport becomes a magnifier, not an occlusion) — freeze until it ends.
      if (vv && Math.abs(vv.scale - 1) > 0.01) return

      const layoutHeight = root.clientHeight
      const hiddenTop = standaloneStatusBarGap(
        isStandaloneDisplay(window),
        window.screen.height,
        layoutHeight,
        safeTopProbe.offsetHeight
      )
      const m = vv
        ? computeViewportMetrics(layoutHeight, vv.height, vv.offsetTop, hiddenTop)
        : computeViewportMetrics(layoutHeight, layoutHeight, 0, hiddenTop)

      const keyboard = editableFocused && m.bottomInset >= KEYBOARD_MIN_PX ? m.bottomInset : 0

      root.style.setProperty('--vvh', `${m.height}px`)
      root.style.setProperty('--vv-top', `${m.offsetTop}px`)
      root.style.setProperty('--vv-bottom', `${m.bottomInset}px`)
      root.style.setProperty('--kb', `${keyboard}px`)

      if (keyboard > 0) root.setAttribute('data-keyboard', 'open')
      else root.removeAttribute('data-keyboard')

      // iOS keeps fixed elements painted against a stale layout-viewport origin
      // after the keyboard collapses — the "weird padding that's there until I
      // scroll". Scrolling to 0 forces the relayout that otherwise waits for
      // the user. Cheap, idempotent, and a no-op on a non-scrolling document.
      if (lastKeyboard > 0 && keyboard === 0) window.scrollTo(0, 0)
      lastKeyboard = keyboard
    }

    const schedule = () => {
      if (scheduled) return
      scheduled = true
      frame = requestAnimationFrame(() => {
        scheduled = false
        write()
      })
    }

    const onFocusIn = (e: FocusEvent) => {
      window.clearTimeout(blurTimer)
      const t = e.target
      editableFocused = t instanceof Element && t.matches(EDITABLE)
      schedule()
    }
    const onFocusOut = () => {
      window.clearTimeout(blurTimer)
      blurTimer = window.setTimeout(() => {
        editableFocused = false
        schedule()
      }, BLUR_SETTLE_MS)
    }

    write()
    // Both listeners are required: iOS offsets the visual viewport WITHOUT
    // resizing it, which fires scroll and no resize at all.
    vv?.addEventListener('resize', schedule)
    vv?.addEventListener('scroll', schedule)
    window.addEventListener('orientationchange', schedule)
    window.addEventListener('pageshow', schedule) // bfcache restore
    document.addEventListener('focusin', onFocusIn)
    document.addEventListener('focusout', onFocusOut)
    if (!vv) window.addEventListener('resize', schedule)

    return () => {
      if (frame) cancelAnimationFrame(frame)
      window.clearTimeout(blurTimer)
      vv?.removeEventListener('resize', schedule)
      vv?.removeEventListener('scroll', schedule)
      window.removeEventListener('orientationchange', schedule)
      window.removeEventListener('pageshow', schedule)
      document.removeEventListener('focusin', onFocusIn)
      document.removeEventListener('focusout', onFocusOut)
      if (!vv) window.removeEventListener('resize', schedule)
      for (const prop of ['--vvh', '--vv-top', '--vv-bottom', '--kb']) {
        root.style.removeProperty(prop)
      }
      root.removeAttribute('data-keyboard')
      safeTopProbe.remove()
    }
  }, [])
}
