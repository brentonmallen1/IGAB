import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { moneyOrDash } from '../../utils/money'
import type { Liability } from '../../api/liabilities'
import { Surface } from '../common/Surface'
import { ledgerAgreementNote, pmiNote, type CompositionNote } from './compositionNotes'
import './PaymentBreakdown.css'

const ICON = {
  ok: CheckCircle2,
  warn: AlertTriangle,
  info: Info,
} as const

function Note({ note }: { note: CompositionNote }) {
  const Icon = ICON[note.tone]
  return (
    <p className={`payment-breakdown__note payment-breakdown__note--${note.tone}`}>
      <Icon size={13} aria-hidden />
      <span>{note.text}</span>
    </p>
  )
}

/**
 * What the bill is made of, on the liability page.
 *
 * Renders nothing — no card, no heading — without a composition on file or a
 * disagreement to report, which is every debt that is not an escrowed
 * mortgage. An empty titled section is worse than an absent one.
 *
 * The list is the visibility the feature was asked for: what you actually pay
 * each month, split, so it can be held against a statement. The notes under
 * it are the reason it is worth entering — whether the ledger agrees with the
 * split, and whether the mortgage insurance on it has outlived the equity
 * that justified it. Both decisions live in `compositionNotes.ts`.
 */
export function PaymentBreakdown({
  liability,
  assetValue,
  equity,
  formatMoney,
}: {
  liability: Liability
  /** The linked home's stated value, for the PMI threshold. */
  assetValue: number | null
  equity: number | null
  formatMoney: (n: number) => string
}) {
  const components = liability.payment_components
  const agreement = ledgerAgreementNote(liability, formatMoney)
  const pmi = pmiNote(liability, assetValue, equity, formatMoney)
  if (components.length === 0 && !agreement) return null

  return (
    <Surface
      as="section"
      className="liability-page__section"
      header={
        <div className="liability-page__section-header">
          <h2>What you pay each month</h2>
        </div>
      }
    >
      <div className="liability-page__section-body payment-breakdown">
        {components.length > 0 && liability.minimum_payment !== null && (
          <dl className="payment-breakdown__list">
            <div className="payment-breakdown__row">
              <dt>Principal &amp; interest</dt>
              <dd className="tabular">{formatMoney(Number(liability.minimum_payment))}</dd>
            </div>
            {components.map((c, i) => (
              <div className="payment-breakdown__row" key={`${c.kind}-${i}`}>
                <dt>{c.label}</dt>
                <dd className="tabular">{formatMoney(c.amount)}</dd>
              </div>
            ))}
            <div className="payment-breakdown__row payment-breakdown__row--total">
              <dt>Your bill each month</dt>
              <dd className="tabular">
                {moneyOrDash(liability.full_monthly_payment, formatMoney)}
              </dd>
            </div>
          </dl>
        )}
        {/* Only the P&I line drives a projection; saying so here stops the
          total above from reading as the figure the payoff date used. */}
        {components.length > 0 && (
          <p className="payment-breakdown__caveat">
            Every payoff figure on this page is computed from the principal and interest line alone.
          </p>
        )}
        {agreement && <Note note={agreement} />}
        {pmi && <Note note={pmi} />}
      </div>
    </Surface>
  )
}
