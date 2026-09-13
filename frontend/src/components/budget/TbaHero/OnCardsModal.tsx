import { useState } from 'react'
import { CreditCard } from 'lucide-react'
import { useBudgetMonth } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { Dialog } from '../../common/Dialog/Dialog'
import { Collapsible } from '../../common/Collapsible/Collapsible'
import { TransactionsPeekModal } from '../TransactionsPeekModal/TransactionsPeekModal'
import './OnCardsModal.css'

interface Props {
  budgetId: string
  month: string
  onClose: () => void
}

/**
 * What the hero's "on cards" figure is made of.
 *
 * That figure is the part of this month's overspending that was swiped on a
 * card, so it rides there as debt instead of charging Ready to Assign. Cover
 * Overspending funds it like any other red — the money lands in the card's
 * set-aside and retires the debt — but which envelope rode onto which card is
 * still the question a card carrying debt raises, and nothing on the page
 * could answer it. The breakdown is served (`overspent_by_category` on each
 * card row, from `CardFunding.floored_by_pair`) because the allocation is a
 * running walk per (category, card) that no client can reproduce.
 *
 * Grouped by card because cards are paid separately: which one carries the
 * debt decides where the next assignment goes. Each envelope row opens the
 * ordinary transactions peek, so "which spending was that?" is one click away
 * without this dialog inventing a per-transaction attribution the model does
 * not have — the ride is a month's net, not a set of rows.
 */
export function OnCardsModal({ budgetId, month, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const cards = (budgetMonth?.cards ?? []).filter((c) => c.overspent_this_month > 0)
  const total = cards.reduce((sum, c) => sum + c.overspent_this_month, 0)

  // One card is the common case and its group carries no information when
  // collapsed, so it opens; with several, the list is the thing to read first.
  const [openCards, setOpenCards] = useState<Record<string, boolean>>(() =>
    cards.length === 1 ? { [cards[0].account_id]: true } : {}
  )
  const [peek, setPeek] = useState<{ id: string; name: string } | null>(null)

  return (
    <>
      <Dialog
        title="Overspending on cards"
        onClose={onClose}
        historyKey="on-cards"
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
            {formatMoney(total)} of this month&rsquo;s spending was swiped on a card with no money
            behind it in its envelope. It rides on the card as debt — already counted in that
            card&rsquo;s <strong>Uncovered</strong> — and never charged Ready to Assign. Retire it
            by funding these envelopes in this month (Cover Overspending does exactly that), or by
            assigning straight to the card.
          </p>

          {cards.map((card) => (
            <Collapsible
              key={card.account_id}
              className="on-cards__group"
              title={card.name}
              count={card.overspent_by_category.length}
              meta={formatMoney(-card.overspent_this_month)}
              isOpen={!!openCards[card.account_id]}
              onToggle={() =>
                setOpenCards((open) => ({
                  ...open,
                  [card.account_id]: !open[card.account_id],
                }))
              }
            >
              <ul className="on-cards__list">
                {card.overspent_by_category.map((rode) => (
                  <li key={rode.category_id} className="on-cards__row">
                    <button
                      type="button"
                      className="on-cards__category"
                      onClick={() => setPeek({ id: rode.category_id, name: rode.category_name })}
                      title={`Transactions in ${rode.category_name}`}
                    >
                      {rode.category_name}
                    </button>
                    <span className="on-cards__amount tabular">{formatMoney(-rode.amount)}</span>
                  </li>
                ))}
              </ul>
              {/* Said per card, not once at the top: the remedy is per card,
                  and a reader who opened one group is asking about that one. */}
              <p className="on-cards__group-note">
                <CreditCard size={12} aria-hidden />
                Funding these envelopes for this month retires this debt; so does assigning to{' '}
                {card.name} in the Credit cards section.
              </p>
            </Collapsible>
          ))}
        </div>
      </Dialog>
      {peek && (
        <TransactionsPeekModal
          budgetId={budgetId}
          scope={{ kind: 'category', categoryId: peek.id, categoryName: peek.name }}
          onClose={() => setPeek(null)}
        />
      )}
    </>
  )
}
