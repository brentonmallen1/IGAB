import { useEffect } from 'react'
import { useAppStore } from '../../stores/appStore'
import { buildId } from '../../hooks/useViewportDiagnostics'
import { RULER_LINES } from './viewportRulerLines'
import './ViewportRuler.css'

/**
 * Labelled hairlines at every edge the shell's height is computed from, so a
 * screenshot from the phone says which number is wrong without anybody
 * subtracting. Pointer-transparent; toggled from Settings → Mobile or with
 * `?vvdebug=1` on the URL, and remembered per device so it survives moving
 * between pages.
 *
 * Each line's position is a CSS expression, not a measured number: the ruler
 * shows where CSS itself puts things, which is the question.
 */
export function ViewportRuler() {
  const on = useAppStore((s) => s.viewportRulerOn)
  const setViewportRuler = useAppStore((s) => s.setViewportRuler)

  // A way in that needs no navigation: the band is on /budget, and Settings
  // is three taps away through a sheet that may itself be misbehaving.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('vvdebug') === '1') setViewportRuler(true)
  }, [setViewportRuler])

  if (!on) return null
  return (
    <div className="viewport-ruler" aria-hidden="true" data-testid="viewport-ruler">
      {RULER_LINES.map((line) => (
        <div
          key={line.id}
          className={`viewport-ruler__line viewport-ruler__line--${line.tone}`}
          style={line.style}
          data-line={line.id}
        >
          <span className="viewport-ruler__label">{line.label}</span>
        </div>
      ))}
      <div className="viewport-ruler__badge">{buildId()}</div>
    </div>
  )
}
