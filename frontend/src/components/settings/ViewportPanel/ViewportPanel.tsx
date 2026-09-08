import { useState } from 'react'
import { useAppStore } from '../../../stores/appStore'
import { diagnoseGap, useViewportDiagnostics } from '../../../hooks/useViewportDiagnostics'
import './ViewportPanel.css'

/**
 * The raw viewport numbers and what they say, for reading off a phone.
 *
 * Lives inside the app shell on purpose: the header, the bottom nav and every
 * token are live here, so the numbers are the ones the budget page is drawn
 * with. See useViewportDiagnostics for why this exists.
 */

const VERDICT_TEXT = {
  none: 'The shell fills the screen.',
  'status-bar-hidden':
    'Short by the status bar: every reported height excludes the top inset while the screen paints it. The shell corrects for this; if a band still shows, screenshot the ruler.',
  other: 'Short by something that is not the top inset. Turn the ruler on and screenshot /budget.',
} as const

type SwState = 'idle' | 'checking' | 'current' | 'waiting' | 'unsupported'

export function ViewportPanel() {
  const snap = useViewportDiagnostics()
  const rulerOn = useAppStore((s) => s.viewportRulerOn)
  const setViewportRuler = useAppStore((s) => s.setViewportRuler)
  const [sw, setSw] = useState<SwState>('idle')

  async function checkForUpdate() {
    if (!('serviceWorker' in navigator)) {
      setSw('unsupported')
      return
    }
    setSw('checking')
    try {
      const reg = await navigator.serviceWorker.getRegistration()
      if (!reg) {
        setSw('unsupported')
        return
      }
      await reg.update()
      setSw(reg.waiting ? 'waiting' : 'current')
    } catch {
      setSw('unsupported')
    }
  }

  const rows: Array<[string, string | number]> = snap
    ? [
        ['Display mode', `${snap.displayMode}${snap.standalone ? ' (standalone)' : ''}`],
        ['Web build', snap.buildId],
        ['screen', `${snap.screenW} × ${snap.screenH}`],
        ['innerHeight / outerHeight', `${snap.innerH} / ${snap.outerH}`],
        ['documentElement.clientHeight', snap.clientH],
        ['visualViewport height / top / scale', `${snap.vvH} / ${snap.vvTop} / ${snap.vvScale}`],
        [
          '--safe-top / --safe-bottom',
          `${snap.tokens['--safe-top']} / ${snap.tokens['--safe-bottom']}`,
        ],
        ['--vvh / --app-h', `${snap.tokens['--vvh']} / ${snap.tokens['--app-h']}`],
        ['--nav-h / --kb', `${snap.tokens['--nav-h']} / ${snap.tokens['--kb']}`],
        ['screen − layout', snap.screenH - snap.clientH],
        ['screen − visual', snap.screenH - snap.vvH],
        ['screen − app-h', snap.screenH - snap.tokens['--app-h']],
      ]
    : []

  return (
    <div className="viewport-panel">
      <div className="settings-row">
        <div>
          <div className="settings-row__label">Viewport</div>
          <div className="settings-row__desc">
            {snap ? VERDICT_TEXT[diagnoseGap(snap)] : 'Measuring…'}
          </div>
        </div>
      </div>

      <dl className="viewport-panel__grid">
        {rows.map(([k, v]) => (
          <div key={k} className="viewport-panel__row">
            <dt>{k}</dt>
            <dd className="tabular">{v}</dd>
          </div>
        ))}
      </dl>

      <div className="settings-row">
        <div>
          <div className="settings-row__label">Show ruler</div>
          <div className="settings-row__desc">
            Draws labelled lines at every edge the layout is computed from, on every page, until
            switched off.
          </div>
        </div>
        <input
          type="checkbox"
          checked={rulerOn}
          onChange={(e) => setViewportRuler(e.target.checked)}
          aria-label="Show viewport ruler"
        />
      </div>

      <div className="settings-row">
        <div>
          <div className="settings-row__label">Check for update now</div>
          <div className="settings-row__desc">
            {sw === 'idle' && 'Asks the service worker whether a newer build is on the server.'}
            {sw === 'checking' && 'Checking…'}
            {sw === 'current' && 'This is the latest build the server has.'}
            {sw === 'waiting' && 'A newer build is downloaded — the update prompt will show it.'}
            {sw === 'unsupported' && 'No service worker here (dev server, or not installed).'}
          </div>
        </div>
        <button className="settings-btn settings-btn--secondary" onClick={checkForUpdate}>
          Check
        </button>
      </div>
    </div>
  )
}
