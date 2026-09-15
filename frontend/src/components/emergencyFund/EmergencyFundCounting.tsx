import { useState } from 'react'
import { useEmergencyFund } from '../../api/emergencyFund'
import { useFormatters } from '../../hooks/useFormatters'
import type { EmergencyFund } from '../../types'
import { countingLine } from './countingLine'
import { EmergencyFundPicker } from './EmergencyFundPicker'
import './EmergencyFundCounting.css'

/**
 * "Counting: Emergency Fund envelope $2,400.00 · Harborstone Reserve $6,000.00
 * [Change]" — or "Not set up — [Choose what counts]".
 *
 * Presentational: renders from a fund object and fetches nothing, so an
 * explainer can show it with an invented fixture. Without `onChange` there is
 * no button (an example has nothing to change).
 */
export function EmergencyFundCountingView({
  fund,
  onChange,
}: {
  fund: EmergencyFund
  onChange?: () => void
}) {
  const { formatMoney } = useFormatters()
  const line = countingLine(fund, formatMoney)
  return (
    <p className="ef-counting">
      {line ? (
        <>
          <span className="ef-counting__label">Counting:</span> <span>{line}</span>
        </>
      ) : (
        <span className="ef-counting__label">Not set up —</span>
      )}
      {onChange && (
        <>
          {' '}
          <button type="button" className="ef-counting__change" onClick={onChange}>
            {line ? 'Change' : 'Choose what counts'}
          </button>
        </>
      )}
    </p>
  )
}

/**
 * The Counting line every surface that quotes the emergency fund shows, and
 * the picker behind its button. Reads `useEmergencyFund` only — one source, so
 * the Essentials report, the Emergency Fund report, the sizer, the Guide and
 * Settings → Tags cannot say different things about what was counted.
 */
export function EmergencyFundCounting({ budgetId, from }: { budgetId: string; from?: 'guide' }) {
  const { data } = useEmergencyFund(budgetId)
  const [open, setOpen] = useState(false)
  if (!data) return null
  return (
    <>
      <EmergencyFundCountingView fund={data.fund} onChange={() => setOpen(true)} />
      {open && (
        <EmergencyFundPicker budgetId={budgetId} from={from} onClose={() => setOpen(false)} />
      )}
    </>
  )
}
