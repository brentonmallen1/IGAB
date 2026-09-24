import { useBudgetMonth } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { Dialog } from '../../common/Dialog/Dialog'
import './OnCardsModal.css'

interface Props {
  budgetId: string
  month: string
  onClose: () => void
}

/**
 * Where the money went, when Ready to Assign is lower than the envelopes
 * alone would say.
 *
 * A card's Set aside enters the envelope total signed, so paying a card past
 * what its envelope held used to LEAVE Ready to Assign where it was — the
 * household had $100 less in the bank and a page saying it could still assign
 * the $100, until someone assigned it to the card and made the page true.
 * The figure is corrected now (`paid_ahead_on_cards`, subtracted server-side),
 * and a number that moves needs its reason beside it. This is the reason, in
 * two sentences, with the cards it came from.
 *
 * Only the unmirrored part is here. A refund that landed as residual, a card
 * holding a credit, money released out of the envelope — each of those
 * negatives is matched by a positive somewhere on the page, and Ready to
 * Assign was already right about them. The server decides which is which
 * (`domain/cards.py` `unmirrored_shortfall`); this only lists what it served.
 */
export function PaidAheadModal({ budgetId, month, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const total = budgetMonth?.paid_ahead_on_cards ?? 0
  const cards = (budgetMonth?.cards ?? []).filter((c) => c.paid_ahead_unmirrored > 0)

  return (
    <Dialog
      title="Paid ahead on cards"
      onClose={onClose}
      historyKey="paid-ahead-on-cards"
      className="on-cards"
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
      <div className="on-cards__body">
        <p className="on-cards__description">
          You paid {formatMoney(total)} toward these cards beyond what their envelopes held. That
          money has left your account, so it is not here to assign — Ready to Assign already
          reflects it. Assigning to a card squares its envelope; it does not change Ready to Assign
          again.
        </p>
        <ul className="on-cards__list" aria-label="Cards paid ahead">
          {cards.map((card) => (
            <li key={card.account_id} className="on-cards__row">
              <span>{card.name}</span>
              <span className="on-cards__amount tabular">
                {formatMoney(card.paid_ahead_unmirrored)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Dialog>
  )
}
