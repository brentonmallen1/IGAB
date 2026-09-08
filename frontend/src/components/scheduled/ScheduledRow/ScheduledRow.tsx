import type { ScheduledTransaction } from '../../../types'
import { useFormatters } from '../../../hooks/useFormatters'
import { daysUntil, dueLabel, dueState, frequencyLabel } from '../../../utils/schedule'
import './ScheduledRow.css'

/**
 * A scheduled transaction as a row — the one implementation.
 *
 * It was drawn twice: the register's "Upcoming" section had an eight-column
 * desktop grid and no phone layout at all (the first thing a phone showed on
 * any account was a row 400px wider than the screen), and the Scheduled page
 * had a seven-column grid with a proper card restack. Two copies, one of
 * which knew what a phone was.
 *
 * One DOM, two desktop shapes, one phone card. `layout` picks the desktop
 * column set — `register` lines up under the register (date, payee,
 * category, memo, amount, actions); `table` is the Scheduled page's
 * (account, payee, amount, frequency, date, auto, actions). Every cell is
 * always rendered; the stylesheet shows and hides per layout, so the phone
 * card is written once and cannot drift between the two.
 */

export interface ScheduledRowProps {
  scheduled: ScheduledTransaction
  /** Display names resolved by the caller, which owns the lookups. */
  names: { payee: string; category?: string; account?: string }
  layout: 'register' | 'table'
  todayISO: string
  onEdit: () => void
  onEnter: () => void
  onSkip: () => void
  /** An enter or skip is in flight — both buttons wait. */
  busy?: boolean
}

export function ScheduledRow({
  scheduled: s,
  names,
  layout,
  todayISO,
  onEdit,
  onEnter,
  onSkip,
  busy = false,
}: ScheduledRowProps) {
  const { formatMoney } = useFormatters()
  const due = dueState(s, todayISO)
  const out = s.amount < 0

  return (
    <div
      className={`scheduled-row scheduled-row--${layout}`}
      role="button"
      tabIndex={0}
      onClick={onEdit}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onEdit()
        }
      }}
      data-testid="scheduled-row"
    >
      <span className="scheduled-row__account txn-text-clip">{names.account ?? ''}</span>
      <span className="scheduled-row__payee txn-text-clip">{names.payee}</span>
      <span className="scheduled-row__category txn-text-clip">{names.category ?? '—'}</span>
      <span className="scheduled-row__memo txn-text-clip">{s.memo ?? ''}</span>
      <span className={`scheduled-row__amount tabular ${out ? 'negative' : 'positive'}`}>
        {formatMoney(Math.abs(s.amount))}
        <span className="scheduled-row__direction">{out ? ' out' : ' in'}</span>
      </span>
      <span className="scheduled-row__freq">{frequencyLabel(s.frequency)}</span>
      <span className="scheduled-row__date">
        {s.next_occurrence_date}
        {due && (
          <span className={`scheduled-row__due scheduled-row__due--${due}`}>
            {dueLabel(daysUntil(s.next_occurrence_date, todayISO))}
          </span>
        )}
      </span>
      <span className="scheduled-row__auto">{s.auto_create ? 'Yes' : '—'}</span>
      <span className="scheduled-row__actions" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="scheduled-row__btn"
          title="Enter now"
          onClick={onEnter}
          disabled={busy}
        >
          Enter
        </button>
        <button
          type="button"
          className="scheduled-row__btn scheduled-row__btn--secondary"
          title="Skip to next"
          onClick={onSkip}
          disabled={busy}
        >
          Skip
        </button>
      </span>
    </div>
  )
}

/** The Scheduled page's column headings — same stylesheet, same template. */
export function ScheduledTableHead() {
  return (
    <div className="scheduled-row__head" aria-hidden="true">
      <span>Account</span>
      <span>Payee</span>
      <span>Amount</span>
      <span>Frequency</span>
      <span>Next Date</span>
      <span>Auto</span>
      <span></span>
    </div>
  )
}
