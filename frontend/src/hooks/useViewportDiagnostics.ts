import { useEffect, useState } from 'react'
import { isStandaloneDisplay } from './useAppViewport'

/**
 * Every number that decides how tall the app shell is, read raw and shown to
 * the person holding the phone.
 *
 * Exists because the band under the bottom nav in the installed iOS PWA
 * survived two fixes that each reasoned correctly from a number that turned
 * out to be wrong on hardware (100dvh, then visualViewport.height), and
 * nothing short of a screenshot could say which. Chrome cannot emulate the
 * standalone insets and jsdom has no layout, so the diagnosis has to happen
 * on the device — this hook is what the Settings → Mobile panel and the
 * on-screen ruler read.
 *
 * Tokens are read off PROBE elements (`height: var(--x)`) via computed style,
 * not `getPropertyValue`, which returns the declaration text — `env(...)`
 * unevaluated — and is no use as a number.
 */

export const PROBE_TOKENS = [
  '--safe-top',
  '--safe-bottom',
  '--vvh',
  '--app-h',
  '--nav-h',
  '--kb',
] as const
export type ProbeToken = (typeof PROBE_TOKENS)[number]

export interface ViewportSnapshot {
  displayMode: string
  standalone: boolean
  screenW: number
  screenH: number
  innerH: number
  outerH: number
  clientH: number
  vvH: number
  vvTop: number
  vvScale: number
  tokens: Record<ProbeToken, number>
  buildId: string
}

const DISPLAY_MODES = ['fullscreen', 'standalone', 'minimal-ui', 'browser'] as const

function displayMode(win: Window): string {
  if (typeof win.matchMedia !== 'function') return 'unknown'
  for (const mode of DISPLAY_MODES) {
    if (win.matchMedia(`(display-mode: ${mode})`).matches) return mode
  }
  return 'unknown'
}

/** Pure over its inputs: the window and the probe heights already measured. */
export function readViewportSnapshot(
  win: Window,
  tokens: Record<ProbeToken, number>,
  buildId: string
): ViewportSnapshot {
  const vv = win.visualViewport
  const layout = win.document.documentElement
  return {
    displayMode: displayMode(win),
    standalone: isStandaloneDisplay(win),
    screenW: Math.round(win.screen.width),
    screenH: Math.round(win.screen.height),
    innerH: Math.round(win.innerHeight),
    outerH: Math.round(win.outerHeight),
    clientH: Math.round(layout.clientHeight),
    vvH: Math.round(vv?.height ?? layout.clientHeight),
    vvTop: Math.round(vv?.offsetTop ?? 0),
    vvScale: vv ? Math.round(vv.scale * 100) / 100 : 1,
    tokens,
    buildId,
  }
}

export type GapVerdict =
  | 'none' // the shell already fills the screen
  | 'status-bar-hidden' // every reported height is short by the top inset — the iOS standalone case
  | 'other' // short by something that is not the inset; needs the ruler

/**
 * What the numbers say about the band, so the panel can state it outright
 * instead of asking the reader to subtract.
 *
 * Only meaningful in standalone; a browser tab is short by its chrome and
 * that is not a bug.
 */
export function diagnoseGap(s: ViewportSnapshot): GapVerdict {
  if (!s.standalone) return 'none'
  const short = s.screenH - s.clientH
  if (short <= 1) return 'none'
  return Math.abs(short - s.tokens['--safe-top']) <= 1 ? 'status-bar-hidden' : 'other'
}

function mountProbes(doc: Document): { host: HTMLElement; read: () => Record<ProbeToken, number> } {
  const host = doc.createElement('div')
  host.setAttribute('data-viewport-probe', 'tokens')
  host.setAttribute('aria-hidden', 'true')
  Object.assign(host.style, {
    position: 'fixed',
    top: '0',
    left: '0',
    width: '0',
    visibility: 'hidden',
    pointerEvents: 'none',
  })
  const els = {} as Record<ProbeToken, HTMLElement>
  for (const token of PROBE_TOKENS) {
    const el = doc.createElement('div')
    el.style.height = `var(${token})`
    host.appendChild(el)
    els[token] = el
  }
  doc.body.appendChild(host)
  const read = () => {
    const out = {} as Record<ProbeToken, number>
    for (const token of PROBE_TOKENS) {
      // A computed length is always `<n>px`; Number() of the bare figure is exact.
      out[token] = Math.round(Number(getComputedStyle(els[token]).height.replace('px', '')) || 0)
    }
    return out
  }
  return { host, read }
}

declare const __BUILD_ID__: string

export function buildId(): string {
  return typeof __BUILD_ID__ === 'string' ? __BUILD_ID__ : 'dev'
}

/** Live snapshot; re-reads on every visual-viewport change like useAppViewport. */
export function useViewportDiagnostics(): ViewportSnapshot | null {
  const [snapshot, setSnapshot] = useState<ViewportSnapshot | null>(null)

  useEffect(() => {
    const { host, read } = mountProbes(document)
    const vv = window.visualViewport
    let frame = 0
    const schedule = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() =>
        setSnapshot(readViewportSnapshot(window, read(), buildId()))
      )
    }
    schedule()
    vv?.addEventListener('resize', schedule)
    vv?.addEventListener('scroll', schedule)
    window.addEventListener('resize', schedule)
    window.addEventListener('orientationchange', schedule)
    return () => {
      cancelAnimationFrame(frame)
      vv?.removeEventListener('resize', schedule)
      vv?.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      window.removeEventListener('orientationchange', schedule)
      host.remove()
    }
  }, [])

  return snapshot
}
