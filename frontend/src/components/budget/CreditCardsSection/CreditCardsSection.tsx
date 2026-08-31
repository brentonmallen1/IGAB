import { useState } from 'react'
import { ChevronDown, ChevronRight, CreditCard, Crosshair, Info } from 'lucide-react'
import { useBudgetMonth, useSetAssignment } from '../../../api/budgets'
import { useTarget } from '../../../api/targets'
import { TargetEditor } from '../TargetEditor'
import { useFormatters } from '../../../hooks/useFormatters'
import { useUIStore } from '../../../stores/uiStore'
import { parseAssignmentCommit } from '../../../utils/amountExpression'
import { Dialog } from '../../common/Dialog/Dialog'
import { Surface } from '../../common/Surface'
import { TransactionsPeekModal } from '../TransactionsPeekModal/TransactionsPeekModal'
import type { CardStatus } from '../../../types'
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
/**
 * The five legs a card's Ready to pay is the running total of, plus what is
 * still riding on the card uncovered.
 *
 * Served, never summed here: `set_aside` already comes from the server, and a
 * client-side second opinion about what a reserve is made of is the exact
 * shape of the defect that put this panel here — an assignment that landed in
 * the reserve while the debt it covered rode outside it, so the reserve
 * converged on what the card owed plus every dollar ever assigned to it
 * ("Two Ledgers, One Debt").
 */
function ReserveLegs({
  card,
  formatMoney,
}: {
  card: CardStatus
  formatMoney: (n: number) => string
}) {
  const legs = [
    { label: 'Assigned to this card', value: card.assigned, sign: '+' },
    { label: 'Set aside by funded spending', value: card.reserved, sign: '+' },
    { label: 'Released by refunds', value: card.released, sign: '−' },
    { label: 'Refunds beyond what was reserved', value: card.residual, sign: '−' },
    { label: 'Paid to the card', value: card.payments, sign: '−' },
  ].filter((leg) => leg.value !== 0)

  return (
    <div className="credit-cards__legs">
      <dl className="credit-cards__legs-list">
        {legs.length === 0 && (
          <div className="credit-cards__leg credit-cards__leg--empty">
            <dt>Nothing has moved through this card yet.</dt>
          </div>
        )}
        {legs.map((leg) => (
          <div className="credit-cards__leg" key={leg.label}>
            <dt>{leg.label}</dt>
            <dd className="tabular">
              {leg.sign} {formatMoney(Math.abs(leg.value))}
            </dd>
          </div>
        ))}
        <div className="credit-cards__leg credit-cards__leg--total">
          <dt>Ready to pay</dt>
          <dd className="tabular">{formatMoney(card.set_aside)}</dd>
        </div>
      </dl>
      {card.riding !== 0 && (
        <p className="credit-cards__legs-note">
          {formatMoney(card.riding)} of spending rode onto this card without being funded. It is
          outside the total above — assigning to the card is what retires it.
        </p>
      )}
    </div>
  )
}

export function CreditCardsSection({ budgetId, month }: { budgetId: string; month: string }) {
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const setAssignment = useSetAssignment(budgetId)
  const { formatMoney } = useFormatters()
  const collapsed = useUIStore((s) => s.creditCardsCollapsed)
  const toggleCollapsed = useUIStore((s) => s.toggleCreditCardsCollapsed)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [infoOpen, setInfoOpen] = useState(false)
  const [peek, setPeek] = useState<{ accountId: string; accountName: string } | null>(null)
  const [targetFor, setTargetFor] = useState<{ categoryId: string; name: string } | null>(null)
  const [legsFor, setLegsFor] = useState<string | null>(null)

  const cards = budgetMonth?.cards ?? []
  if (cards.length === 0) return null

  const assignedByCategory = new Map(
    budgetMonth?.category_balances.map((b) => [b.category_id, Number(b.assigned ?? 0)]) ?? []
  )
  // The server computes a card envelope's target verdict like any other
  // category's — the grid never draws the envelope, so this strip is where
  // the number surfaces.
  const neededByCategory = new Map(
    budgetMonth?.category_balances.map((b) => [b.category_id, b.needed_this_month]) ?? []
  )
  const totalUncovered = cards.reduce((sum, c) => sum + Number(c.uncovered), 0)

  function commit(categoryId: string, assigned: number) {
    // The same rule the grid's cell uses: empty commits zero, a leading
    // operator adjusts what is already there, negatives are allowed (money
    // can come back off a card), and only unparseable text writes nothing.
    const amount = parseAssignmentCommit(draft, assigned)
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
                Ready to pay
              </span>
              <span role="columnheader" className="credit-cards__col--num">
                Uncovered
              </span>
            </div>
            {cards.map((card) => {
              const assigned = card.category_id
                ? (assignedByCategory.get(card.category_id) ?? 0)
                : 0
              const needed = card.category_id
                ? (neededByCategory.get(card.category_id) ?? null)
                : null
              const legsOpen = legsFor === card.account_id
              return (
                <div className="credit-cards__group" key={card.account_id}>
                <div className="credit-cards__row" role="row">
                  <span className="credit-cards__col--name" role="cell">
                    <CreditCard size={13} aria-hidden />
                    {card.name}
                    {card.is_closed && <span className="credit-cards__closed-tag">Closed</span>}
                    {card.category_id && (
                      <button
                        type="button"
                        className="credit-cards__target-btn"
                        title={`Paydown target for ${card.name}`}
                        aria-label={`Paydown target for ${card.name}`}
                        onClick={() =>
                          setTargetFor({
                            categoryId: card.category_id as string,
                            name: card.name,
                          })
                        }
                      >
                        <Crosshair size={12} aria-hidden />
                      </button>
                    )}
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
                        onBlur={() => commit(card.category_id as string, assigned)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commit(card.category_id as string, assigned)
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
                    {needed !== null && Number(needed) > 0 && (
                      <span
                        className="credit-cards__hint"
                        title="What the paydown target still wants assigned this month"
                      >
                        {formatMoney(Number(needed))} to go
                      </span>
                    )}
                  </span>
                  <span className="credit-cards__col--num" role="cell">
                    {/* The drill-in, like the grid's Activity cell: the
                        number is the door to the rows behind it. */}
                    <button
                      type="button"
                      className="credit-cards__peek-btn tabular"
                      title={`Transactions on ${card.name}`}
                      onClick={() =>
                        setPeek({ accountId: card.account_id, accountName: card.name })
                      }
                    >
                      {formatMoney(card.set_aside)}
                      {Number(card.set_aside) < 0 && (
                        <span className="credit-cards__hint"> overpaid</span>
                      )}
                    </button>
                    {/* Every question this model raised was answered by
                        decomposing this number into the flows behind it, and
                        the surface showed only the total. */}
                    <button
                      type="button"
                      className="credit-cards__legs-btn"
                      aria-expanded={legsOpen}
                      title={legsOpen ? 'Hide what makes this up' : 'What makes this up'}
                      aria-label={`What makes up Ready to pay for ${card.name}`}
                      onClick={() => setLegsFor(legsOpen ? null : card.account_id)}
                    >
                      {legsOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                    </button>
                  </span>
                  <span
                    className="credit-cards__col--num tabular credit-cards__uncovered"
                    role="cell"
                  >
                    {card.uncovered !== 0 ? formatMoney(card.uncovered) : '—'}
                  </span>
                </div>
                {legsOpen && <ReserveLegs card={card} formatMoney={formatMoney} />}
                </div>
              )
            })}
          </div>
        </div>
      )}
      {targetFor && (
        <CardTargetEditor
          categoryId={targetFor.categoryId}
          name={targetFor.name}
          onClose={() => setTargetFor(null)}
        />
      )}
      {peek && (
        <TransactionsPeekModal
          budgetId={budgetId}
          scope={{ kind: 'account', accountId: peek.accountId, accountName: peek.accountName }}
          onClose={() => setPeek(null)}
        />
      )}
      {infoOpen && (
        <Dialog
          title="How credit cards work here"
          onClose={() => setInfoOpen(false)}
          historyKey="credit-cards-info"
        >
          <div className="credit-cards__info">
            <p>
              A card purchase and a cash purchase both spend from an envelope. The difference
              is what happens to your cash: pay cash and the money leaves your account with
              the purchase; pay by card and the envelope is still charged, but the cash it
              gave up is still sitting in your account — the card fronted the purchase. That
              cash cannot go back to Ready to Assign (the bill is coming), so it moves to the
              card's <strong>Ready to pay</strong> and waits.
            </p>
            <div className="credit-cards__example">
              Swipe $60 of groceries on the card → Groceries −$60 · Ready to pay +$60 · your
              cash and Ready to Assign unchanged. Pay the bill → cash −$60 · Ready to pay
              −$60.
            </div>
            <dl>
              <dt>Balance</dt>
              <dd>What the card's ledger says through the viewed month — negative is owed.</dd>
              <dt>Assigned</dt>
              <dd>
                The hand-fed side of Ready to pay: money you moved to the card this month, for
                what no envelope gave up — covering an overspend, or paying down old debt. An
                ordinary assignment: it comes out of Ready to Assign, and undo works.
              </dd>
              <dt>Ready to pay</dt>
              <dd>
                Cash waiting to pay this card, from both sources: what funded envelopes gave
                up when you swiped, plus what you assigned. Payments drain it. Negative means
                payments have outrun it — a credit balance on the card, carried forward until
                new spending or a refund uses it up.
              </dd>
              <dt>Uncovered</dt>
              <dd>
                Owed beyond Ready to pay — overspending that rode onto the card, old debt, or
                a partner's share not yet paid back. Information, not an alarm: a bill that is
                simply not due yet is a normal state. Cover it by assigning to the card
                whenever suits.
              </dd>
            </dl>
            <p>
              <strong>Carrying a balance?</strong> Old debt — including the balance a newly
              linked card arrives with — shows as Uncovered. It charges nothing and nags
              nobody. Paying it down is the Assigned cell: each month, assign what you can
              afford to the card, then pay by transfer from a cash account. Categorize the
              card's new transactions freely — a category only ever gives up money it
              actually has; any shortfall becomes Uncovered, never a charge to Ready to
              Assign.
            </p>
            <p>
              <strong>Uncategorized card rows</strong> move only the card's balance, so they
              sit in Uncovered until filed. Filing them takes nothing you don't have — it
              just tells your reports where the money went. The Guide's roadmap walks the
              whole paydown loop under "Clear high-interest debt."
            </p>
            <p>
              <strong>Paying the card</strong> is a transfer, not a category. When both
              accounts are connected, the two sides of a payment are paired for you as soon
              as they are unmistakable — same amount, a few days apart, nothing else it
              could be. Anything less certain waits on the Accounts page rather than being
              guessed at, because linking the wrong two rows is worse than linking neither.
              Until a payment is paired it has not spent the card's reserve.
            </p>
            <p>
              <strong>Money coming back</strong> to a card only returns to an envelope that
              put it there. A refund of something bought before you started budgeting
              reduces what you owe without releasing any reserved cash, so it pays down
              Uncovered instead — and the envelope shows the amount under its Available, so
              the figure is never lower than you can account for.
            </p>
          </div>
        </Dialog>
      )}
    </Surface>
  )
}

/**
 * The grid's target editor, pointed at a card's set-aside envelope. A tiny
 * wrapper because `useTarget` is a hook and the strip renders cards in a
 * loop — the fetch has to live in a component that exists only while the
 * editor is open.
 */
function CardTargetEditor({
  categoryId,
  name,
  onClose,
}: {
  categoryId: string
  name: string
  onClose: () => void
}) {
  const { data: target, isLoading } = useTarget(categoryId)
  if (isLoading) return null
  return (
    <TargetEditor
      categoryId={categoryId}
      categoryName={name}
      existing={target ?? null}
      onClose={onClose}
    />
  )
}
