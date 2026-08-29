import { useState } from 'react'
import { ChevronDown, ChevronRight, CreditCard, Info } from 'lucide-react'
import { useBudgetMonth, useSetAssignment } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { useUIStore } from '../../../stores/uiStore'
import { parseAmountExpressionInput } from '../../../utils/amountExpression'
import { Dialog } from '../../common/Dialog/Dialog'
import { Surface } from '../../common/Surface'
import './CreditCardsSection.css'

/**
 * The budget's cards — Balance / Set aside / Uncovered, served whole by the
 * month endpoint (`cards` on BudgetMonth; the model is domain/cards.py).
 *
 * A card is not an envelope: its set-aside category never renders in the
 * grid, and Uncovered is deliberately calm — a bill unpaid because the due
 * date is the 8th, or a partner's share still pending, is a normal state,
 * not overspending. Color marks nothing here; the numbers carry it.
 *
 * Sits above the category grid (below the filter bar) and folds shut; the
 * fold is a standing choice, persisted like a collapsed sidebar section.
 * Collapsed, the header still answers the one question worth interrupting
 * for: whether anything is uncovered.
 *
 * "Assigned" edits the card's assignment for the viewed month through the
 * same mutation the grid uses — money to a card is an ordinary assignment,
 * undo included.
 */
export function CreditCardsSection({ budgetId, month }: { budgetId: string; month: string }) {
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const setAssignment = useSetAssignment(budgetId)
  const { formatMoney } = useFormatters()
  const collapsed = useUIStore((s) => s.creditCardsCollapsed)
  const toggleCollapsed = useUIStore((s) => s.toggleCreditCardsCollapsed)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [infoOpen, setInfoOpen] = useState(false)

  const cards = budgetMonth?.cards ?? []
  if (cards.length === 0) return null

  const assignedByCategory = new Map(
    budgetMonth?.category_balances.map((b) => [b.category_id, Number(b.assigned ?? 0)]) ?? []
  )
  const totalUncovered = cards.reduce((sum, c) => sum + Number(c.uncovered), 0)

  function commit(categoryId: string) {
    const amount = parseAmountExpressionInput(draft)
    setEditing(null)
    // NaN = unparseable input: never silently book a number for it.
    if (Number.isNaN(amount)) return
    setAssignment.mutate({ categoryId, month, amount })
  }

  return (
    <Surface
      variant="chrome"
      className={`credit-cards ${collapsed ? 'credit-cards--collapsed' : ''}`}
      headerClassName="credit-cards__header-row"
      header={
        <>
          <button
            type="button"
            className="credit-cards__header"
            onClick={toggleCollapsed}
            aria-expanded={!collapsed}
            aria-controls="credit-cards-body"
          >
            {collapsed ? (
              <ChevronRight size={13} aria-hidden />
            ) : (
              <ChevronDown size={13} aria-hidden />
            )}
            <span className="section-label surface__title">Credit cards</span>
          </button>
          {/* A sibling, not a child: a button cannot nest in the fold control. */}
          <button
            type="button"
            className="credit-cards__info-btn"
            aria-label="How credit cards work here"
            title="How credit cards work here"
            onClick={() => setInfoOpen(true)}
          >
            <Info size={13} aria-hidden />
          </button>
          <span className="credit-cards__summary">
            {cards.length === 1 ? '1 card' : `${cards.length} cards`}
            {totalUncovered !== 0 && <> · {formatMoney(totalUncovered)} uncovered</>}
          </span>
        </>
      }
    >
      {!collapsed && (
        <div id="credit-cards-body" className="credit-cards__body">
          <div className="credit-cards__table" role="table" aria-label="Credit cards">
            <div className="credit-cards__head" role="row">
              <span role="columnheader" className="credit-cards__col--name">
                Card
              </span>
              <span role="columnheader" className="credit-cards__col--num">
                Balance
              </span>
              <span role="columnheader" className="credit-cards__col--num">
                Assigned
              </span>
              <span role="columnheader" className="credit-cards__col--num">
                Set aside
              </span>
              <span role="columnheader" className="credit-cards__col--num">
                Uncovered
              </span>
            </div>
            {cards.map((card) => {
              const assigned = card.category_id
                ? (assignedByCategory.get(card.category_id) ?? 0)
                : 0
              return (
                <div className="credit-cards__row" role="row" key={card.account_id}>
                  <span className="credit-cards__col--name" role="cell">
                    <CreditCard size={13} aria-hidden />
                    {card.name}
                  </span>
                  <span className="credit-cards__col--num tabular" role="cell">
                    {formatMoney(card.balance)}
                  </span>
                  <span className="credit-cards__col--num" role="cell">
                    {card.category_id && editing === card.account_id ? (
                      <input
                        className="credit-cards__assign"
                        autoFocus
                        inputMode="decimal"
                        value={draft}
                        aria-label={`Assigned to ${card.name} this month`}
                        onChange={(e) => setDraft(e.target.value)}
                        onBlur={() => commit(card.category_id as string)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commit(card.category_id as string)
                          if (e.key === 'Escape') setEditing(null)
                        }}
                      />
                    ) : (
                      <button
                        type="button"
                        className="credit-cards__assign-btn tabular"
                        disabled={!card.category_id}
                        title={
                          card.category_id
                            ? 'Assign to this card for the viewed month'
                            : 'This card has no set-aside envelope yet'
                        }
                        onClick={() => {
                          setDraft(assigned ? String(assigned) : '')
                          setEditing(card.account_id)
                        }}
                      >
                        {formatMoney(assigned)}
                      </button>
                    )}
                  </span>
                  <span className="credit-cards__col--num tabular" role="cell">
                    {formatMoney(card.set_aside)}
                  </span>
                  <span
                    className="credit-cards__col--num tabular credit-cards__uncovered"
                    role="cell"
                  >
                    {card.uncovered !== 0 ? formatMoney(card.uncovered) : '—'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
      {infoOpen && (
        <Dialog
          title="How credit cards work here"
          onClose={() => setInfoOpen(false)}
          historyKey="credit-cards-info"
        >
          <div className="credit-cards__info">
            <p>
              A card never touches Ready to Assign on its own. Spending on it does not take
              money out of the budget — it builds a balance to pay later — and the only way a
              card moves the figure is money you deliberately assign to it.
            </p>
            <dl>
              <dt>Balance</dt>
              <dd>What the card's ledger says through the viewed month — negative is owed.</dd>
              <dt>Assigned</dt>
              <dd>
                Money you put toward the card this month. It is an ordinary assignment: it
                comes out of Ready to Assign and undo works.
              </dd>
              <dt>Set aside</dt>
              <dd>
                Cash reserved to pay the card, kept automatically: spending your envelopes
                could cover flows in, payments draw it down, and assigning adds to it. It can
                run negative when payments outran the reserve — that just means the extra came
                from Ready to Assign.
              </dd>
              <dt>Uncovered</dt>
              <dd>
                What is owed beyond the reserve — overspending that rode onto the card, old
                debt, or a partner's share not yet paid back. It is information, not an alarm:
                a bill that is simply not due yet is a normal state. Cover it by assigning to
                the card whenever suits.
              </dd>
            </dl>
          </div>
        </Dialog>
      )}
    </Surface>
  )
}
