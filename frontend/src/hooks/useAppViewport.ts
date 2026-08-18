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
  /** Visible height in CSS px. */
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
 */
export function computeViewportMetrics(
  layoutHeight: number,
  visualHeight: number,
  visualOffsetTop: number
): ViewportMetrics {
  return {
    height: Math.round(visualHeight),
    offsetTop: Math.max(0, Math.round(visualOffsetTop)),
    bottomInset: Math.max(0, Math.round(layoutHeight - visualHeight - visualOffsetTop)),
  }
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
      const m = vv
        ? computeViewportMetrics(layoutHeight, vv.height, vv.offsetTop)
        : computeViewportMetrics(layoutHeight, layoutHeight, 0)

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
    }
  }, [])
}
