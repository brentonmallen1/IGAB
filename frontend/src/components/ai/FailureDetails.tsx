import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AI_SETTINGS_HREF } from '../../pages/SettingsPage/settingsSections'
import type { ScanFailure } from '../transactions/TransactionEditor/scanFailure'
import './FailureDetails.css'

interface Props {
  failure: ScanFailure
  /** `banner`: the review banner, where the person acts — the next step is
   *  in view and only the evidence waits behind Details. `row`: a Scans row
   *  in a list — the headline alone, everything else behind Details. */
  variant: 'banner' | 'row'
}

/** A failed scan or description in layers: the headline, what to do (with
 *  the setting that helps, by its on-screen name), and the evidence. The one
 *  rendering of `jobFailure` — the banner and the Scans row differ only in
 *  what Details hides. */
export function FailureDetails({ failure, variant }: Props) {
  const [open, setOpen] = useState(false)
  const nextStep = (failure.nextStep || failure.settings) && (
    <span className="failure-details__next">
      {failure.nextStep}
      {failure.settings && (
        <>
          {' '}
          <Link to={AI_SETTINGS_HREF} className="failure-details__link">
            Open {failure.settings}
          </Link>
        </>
      )}
    </span>
  )
  const nextStepInView = variant === 'banner'
  const hidden = nextStepInView ? failure.technical : nextStep || failure.technical
  return (
    <span className={`failure-details failure-details--${variant}`}>
      <strong className="failure-details__headline">{failure.headline}</strong>
      {nextStepInView && nextStep}
      {hidden && (
        <button
          type="button"
          className="failure-details__toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          Details
        </button>
      )}
      {open && !nextStepInView && nextStep}
      {open && failure.technical && (
        <pre className="failure-details__technical">{failure.technical}</pre>
      )}
    </span>
  )
}
