import type { ReactNode } from 'react'
import { useFormatters } from '../../../hooks/useFormatters'
import { Dialog } from '../../common/Dialog/Dialog'
import './EnvelopeListDialog.css'

export interface EnvelopeListRow {
  key: string
  name: string
  /** Signed as the dialog should print it. */
  amount: number
  /** When set, the name is a button that opens this envelope's transactions. */
  onOpen?: () => void
}

/**
 * Envelopes and an amount each, with the total under them, behind a pill or a
 * link that carries only the total.
 *
 * Two surfaces list envelopes this way: what the 1st took out of Ready to
 * Assign (the header's "overspent last month"), and what rode onto a card this
 * month (an opened card). The second was a sentence naming every envelope in
 * a row, which a long month turns into a paragraph. Every figure is served;
 * this names and lists them.
 */
export function EnvelopeListDialog({
  title,
  historyKey,
  lede,
  rows,
  total,
  tone,
  onClose,
}: {
  title: string
  historyKey: string
  lede: ReactNode
  rows: EnvelopeListRow[]
  total: number
  /** Overspending already written off reads red; debt still riding on a
   *  card reads as a warning, like the card's own "not covered". */
  tone: 'negative' | 'warning'
  onClose: () => void
}) {
  const { formatMoney } = useFormatters()
  return (
    <Dialog
      title={title}
      onClose={onClose}
      historyKey={historyKey}
      className={`envelope-list envelope-list--${tone}`}
      footer={
        <div className="dialog-actions">
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      }
    >
      <p className="envelope-list__lede">{lede}</p>
      <dl className="envelope-list__list">
        {rows.map((row) => (
          <div className="envelope-list__row" key={row.key}>
            <dt>
              {row.onOpen ? (
                <button type="button" className="envelope-list__open" onClick={row.onOpen}>
                  {row.name}
                </button>
              ) : (
                row.name
              )}
            </dt>
            <dd className="tabular">{formatMoney(row.amount)}</dd>
          </div>
        ))}
        <div className="envelope-list__row envelope-list__row--total">
          <dt>Total</dt>
          <dd className="tabular">{formatMoney(total)}</dd>
        </div>
      </dl>
    </Dialog>
  )
}
