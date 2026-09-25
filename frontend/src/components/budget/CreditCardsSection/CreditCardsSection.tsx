import { Fragment, useId, useRef, useState } from 'react'
import {
  ArrowRightLeft,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  Crosshair,
  TrendingDown,
} from 'lucide-react'
import { useBudgetMonth, useCardTimeline, useSetAssignment } from '../../../api/budgets'
import type { CardTimelineBreach } from '../../../api/budgets'
import { useLiabilities } from '../../../api/liabilities'
import { useAccounts } from '../../../api/accounts'
import { currentMonthStart, today } from '../../../utils/dates'
import { dueSoonNotice, type DueNotice } from '../../../utils/paymentDue'
import { useTarget } from '../../../api/targets'
import { TargetEditor } from '../TargetEditor'
import { useFormatters } from '../../../hooks/useFormatters'
import { useUIStore } from '../../../stores/uiStore'
import { parseAssignmentCommit } from '../../../utils/amountExpression'
import {
  debtMovementLabel,
  debtMovementWord,
  driftSentence,
  dueHeaderNote,
  emptyLegsNote,
  pendingNote,
  reserveLegs,
  releaseAnchors,
  rideMonths,
  otherCredits,
  calmSentence,
  cardLine,
  stateSentence,
} from './cardRow'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { MoveMoneyForm } from '../MoveMoneyPopover/MoveMoneyForm'
import { MoveMoneyPopover } from '../MoveMoneyPopover/MoveMoneyPopover'
import { useCategories } from '../../../api/categories'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { Surface } from '../../common/Surface'
import { Link } from 'react-router-dom'
import { TransactionsPeekModal } from '../TransactionsPeekModal/TransactionsPeekModal'
import type { PeekScope } from '../TransactionsPeekModal/TransactionsPeekModal'
import { overspending } from '../budgetTotals'
import type { CardStatus, Category } from '../../../types'
import { balancesByCategory } from '../../../utils/categoryBalances'
import { CELL_EDITOR_PROPS } from '../../../keyboard/cellEditor'
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
 * The five legs a card's Set aside is the running total of, plus what is
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
  budgetId,
  month,
  card,
  formatMoney,
  formatMonth,
}: {
  budgetId: string
  month: string
  card: CardStatus
  formatMoney: (n: number) => string
  formatMonth: (m: string) => string
}) {
  const [historyOpen, setHistoryOpen] = useState(false)
  const historyId = useId()
  const rides = rideMonths(card)
  const otherInflow = otherCredits(card)
  const pending = pendingNote(card, formatMoney)
  const legs = reserveLegs(card)

  return (
    <div className="credit-cards__legs">
      <dl className="credit-cards__legs-list">
        <div className="credit-cards__leg credit-cards__leg--heading">
          <dt>All time</dt>
        </div>
        {legs.length === 0 && (
          <div className="credit-cards__leg credit-cards__leg--empty">
            <dt>{emptyLegsNote(card)}</dt>
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
          <dt>Set aside</dt>
          <dd className="tabular">{formatMoney(card.set_aside)}</dd>
        </div>
      </dl>
      {/* This month, from the card's own ledger. The legs above are lifetime
        totals, so nothing here can be worked out from them — and the debt
        falling is the one thing a paydown does that the strip never said.

        Every term that moved the balance is a ROW, and every row is SERVED:
        what arrived on the card used to appear only when a client-side plug
        (debt_change + charged − paid) came out non-zero, so a card whose
        only credit was an ordinary payment listed Charged and Paid and
        never named what came in — and the plug, being algebra over the
        other terms, could not fail to reconcile even when they were wrong.
        Received is the whole inflow; the two sub-rows are its split into
        paired payments and everything else. */}
      {(card.charged_this_month !== 0 ||
        card.inflows_this_month !== 0 ||
        card.debt_change_this_month !== 0) && (
        <dl className="credit-cards__legs-list credit-cards__legs-month">
          <div className="credit-cards__leg credit-cards__leg--heading">
            <dt>This month</dt>
          </div>
          <div className="credit-cards__leg">
            <dt>Charged</dt>
            <dd className="tabular">+ {formatMoney(card.charged_this_month)}</dd>
          </div>
          <div className="credit-cards__leg">
            <dt>Received on the card</dt>
            <dd className="tabular">− {formatMoney(card.inflows_this_month)}</dd>
          </div>
          {/* "of which:" in the label, because indentation alone did not carry
            the part-of relationship: a card whose only inflow was unlinked
            read as "Received −$5,380.69 / Other credits $5,380.69" — two rows
            that looked like they cancelled, when the second is the first's
            breakdown. */}
          {card.paid_this_month !== 0 && (
            <div className="credit-cards__leg credit-cards__leg--sub">
              <dt>of which: Paid from your accounts</dt>
              <dd className="tabular">{formatMoney(card.paid_this_month)}</dd>
            </div>
          )}
          {otherInflow !== 0 && (
            <div className="credit-cards__leg credit-cards__leg--sub">
              <dt>
                of which: Other credits<span className="credit-cards__footnote-mark">*</span>
              </dt>
              <dd className="tabular">{formatMoney(otherInflow)}</dd>
            </div>
          )}
          <div className="credit-cards__leg credit-cards__leg--total">
            <dt>Debt {debtMovementWord(card.debt_change_this_month)}</dt>
            <dd className="tabular">{formatMoney(Math.abs(card.debt_change_this_month))}</dd>
          </div>
        </dl>
      )}
      {pending && <p className="credit-cards__legs-note">{pending}</p>}
      {/* The footnote explains the row above it; it no longer carries the
        amount. Only a transfer spends the card's reserve, so a payment
        recorded as a plain deposit lowers the balance while Set aside
        stands still — which is one way a card ends up reserving far more
        than it owes, and why this term is named rather than absorbed. */}
      {otherInflow !== 0 && (
        <p className="credit-cards__legs-note">
          <span className="credit-cards__footnote-mark">*</span> A refund, a credit, or a payment
          whose two halves were never linked. Only a transfer spends Set aside, so this lowers the
          balance while Set aside stands still. Account suggestions, on the Accounts page, lists
          payments that still need linking.
        </p>
      )}
      {/* Two kinds of riding debt, told apart because their remedies differ.
          `riding` is the budget's own — a month ended short and this rode —
          and funding that month retires it. `imported_riding` arrived with
          the budget; no month of ours put it there, so only assigning to the
          card reaches it. They used to share one figure and one sentence, so
          an imported budget read "$2,000 of spending rode onto this card when
          a month ended short" about debt that predates the budget. */}
      {(card.riding !== 0 || card.imported_riding !== 0) && (
        <div className="credit-cards__legs-note credit-cards__riding">
          <p className="section-label credit-cards__riding-title">Riding debt</p>
          {card.riding !== 0 && (
            <p>
              {formatMoney(card.riding)} of spending rode onto this card when a month ended short.
              It sits outside the total above.
            </p>
          )}
          {card.imported_riding !== 0 && (
            <p>
              {formatMoney(card.imported_riding)} came in with the budget as debt nothing was set
              aside for. No month here put it there, so funding an envelope cannot reach it —
              assigning to the card is what retires it.
            </p>
          )}
          {rides.shown.length > 0 && (
            <ul className="credit-cards__ride-months">
              {rides.shown.map((m) => (
                <li key={m.month}>
                  <span>{formatMonth(m.month)}</span>
                  <span className="tabular">{formatMoney(m.amount)}</span>
                </li>
              ))}
              {rides.elided > 0 && (
                <li className="credit-cards__ride-more">
                  and {rides.elided} smaller {rides.elided === 1 ? 'month' : 'months'}
                </li>
              )}
            </ul>
          )}
          {/* The list is what went ON; the total above is what is still there.
            Once an assignment has retired part of it the two disagree, and
            there is no month to attribute the remainder to — the walk records
            a retirement against the assignment's month, not the month that
            rode. Saying so beats pointing at a month already settled. */}
          {rides.retired > 0 && (
            <p>
              {formatMoney(rides.retired)} of that has since been covered by assignments to this
              card, so some of these months are already settled.
            </p>
          )}
          {/* Both ways out, and which is cheaper. The old note named only the
            assignment — the expensive one — and the free remedy went
            unmentioned: the walk is recomputed from scratch every request, so
            raising a past month's assignment retires that month's ride
            retroactively. Funding the FOLLOWING month does not reach back. */}
          {/* The remedy, keyed on whether it works HERE. A shortfall shared
              across cards is handed out in a fixed order, so funding the
              envelope shrinks the first card's ride and this one may not move
              (F8, measured). The server says which; this only reads it. */}
          {card.riding !== 0 && card.ride_reaches_this_card && (
            <p>
              Fund an envelope in the month it ended short and that ride disappears — a backdated
              assignment is re-walked and retires it. If that month has no room to spare, assign to
              the card instead to cover it now.
            </p>
          )}
          {card.riding !== 0 && !card.ride_reaches_this_card && (
            <p>
              That month&rsquo;s shortfall also rode onto another card, and money put into the
              envelope reaches that card first. Assigning to this card is the move that is certain
              to cover it.
            </p>
          )}
        </div>
      )}
      {/* The legs above are lifetime totals; every question a negative one
        raises is about WHEN. The history is served whole — months, deltas,
        and the first month the reserve crossed below zero — and this only
        draws it. */}
      <button
        type="button"
        className="credit-cards__history-btn"
        aria-expanded={historyOpen}
        aria-controls={historyId}
        onClick={() => setHistoryOpen((v) => !v)}
      >
        {historyOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        Month by month
      </button>
      {historyOpen && (
        <ReserveHistory
          id={historyId}
          budgetId={budgetId}
          month={month}
          card={card}
          formatMoney={formatMoney}
          formatMonth={formatMonth}
        />
      )}
    </div>
  )
}

/**
 * A card's reserve, month by month, drawn from the served timeline.
 *
 * Rendering only: the months, each month's delta, the running Set aside,
 * and the breach line all arrive computed (`/cards/{id}/timeline/{month}`,
 * domain/card_timeline.py). Summing a leg here would be the client's second
 * opinion about what a reserve is made of — the defect this whole section
 * exists to end.
 */
function ReserveHistory({
  id,
  budgetId,
  month,
  card,
  formatMoney,
  formatMonth,
}: {
  id: string
  budgetId: string
  month: string
  card: CardStatus
  formatMoney: (n: number) => string
  formatMonth: (m: string) => string
}) {
  // One row open at a time: this is a dense table read at a glance, and a
  // column of expanded rows is the wall of text it is meant to replace.
  const [expanded, setExpanded] = useState<string | null>(null)
  const { data, isPending, isError } = useCardTimeline(budgetId, card.account_id, month)
  if (isPending) {
    return <p className="credit-cards__legs-note">Reading the card's history…</p>
  }
  if (isError || !data) {
    return <p className="credit-cards__legs-note">The history could not be loaded.</p>
  }
  // Newest first. The server walks forward from the first month anything moved,
  // which put the months you opened this to look at — the recent ones — at the
  // bottom of a scroll well ten years long.
  const months = [...data.months].reverse()
  return (
    <div className="credit-cards__history" id={id}>
      {data.breach && (
        <p className="credit-cards__history-breach">
          {breachSentence(data.breach, formatMoney, formatMonth)}
        </p>
      )}
      <div
        className="credit-cards__history-scroll scroll-list"
        role="table"
        aria-label={`Set aside by month for ${card.name}`}
      >
        <div className="credit-cards__history-row credit-cards__history-head" role="row">
          <span role="columnheader">Month</span>
          <span role="columnheader" className="credit-cards__col--num">
            Change
          </span>
          <span role="columnheader" className="credit-cards__col--num">
            Set aside
          </span>
          <span role="columnheader" className="credit-cards__col--num">
            Balance
          </span>
        </div>
        {months.map((m, i) => {
          const year = m.month.slice(0, 4)
          const newYear = i === 0 || months[i - 1].month.slice(0, 4) !== year
          const open = expanded === m.month
          const legs = reserveLegs(m)
          const detailId = `${id}-${m.month}`
          return (
            <Fragment key={m.month}>
              {/* Scrolling down walks backwards in time, so each year is
                  announced as it is entered. */}
              {newYear && (
                <div className="credit-cards__history-year section-label" role="row">
                  <span role="cell">{year}</span>
                </div>
              )}
              <div
                className={[
                  'credit-cards__history-row',
                  // Striped on the data rows' own count. :nth-child would have
                  // counted the sticky header and every year separator.
                  i % 2 === 1 ? 'credit-cards__history-row--alt' : '',
                  data.breach?.month === m.month ? 'credit-cards__history-row--breach' : '',
                  open ? 'credit-cards__history-row--open' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                role="row"
              >
                <span role="cell">
                  {/* A button inside the cell, not instead of it: the row keeps
                      its table semantics. The legs used to live in a `title`
                      tooltip, which on an installed iOS PWA is unreachable. */}
                  <button
                    type="button"
                    className="credit-cards__history-expand"
                    aria-expanded={open}
                    aria-controls={detailId}
                    onClick={() => setExpanded(open ? null : m.month)}
                  >
                    {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                    {formatMonth(m.month)}
                  </button>
                </span>
                <span role="cell" className="credit-cards__col--num tabular">
                  {m.reserve_delta === 0 ? '—' : formatMoney(m.reserve_delta)}
                </span>
                <span role="cell" className="credit-cards__col--num tabular">
                  {formatMoney(m.set_aside)}
                </span>
                <span role="cell" className="credit-cards__col--num tabular">
                  {formatMoney(m.balance)}
                </span>
              </div>
              {open && (
                <div className="credit-cards__history-detail" role="row" id={detailId}>
                  <span role="cell">
                    {legs.length === 0 ? (
                      <p className="credit-cards__history-detail-empty">
                        Nothing moved through Set aside this month.
                      </p>
                    ) : (
                      <dl className="credit-cards__legs-list">
                        {legs.map((leg) => (
                          <div className="credit-cards__leg" key={leg.label}>
                            <dt>{leg.label}</dt>
                            <dd className="tabular">
                              {leg.sign} {formatMoney(Math.abs(leg.value))}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </span>
                </div>
              )}
            </Fragment>
          )
        })}
        {data.anchor_month && months.length > 0 && (
          /* The seam: scrolling down walks backwards in time, so the anchor
             reads where the history ends — a labeled row like the year
             separators, and like them never counted by the striping. */
          <div className="credit-cards__history-year section-label" role="row">
            <span role="cell">
              Imported from YNAB — Set aside started at{' '}
              {formatMoney(months[months.length - 1].set_aside)}; earlier months live in the
              register and reports
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

/** The breach, in a sentence: when, from what to what, and which leg did it. */
function breachSentence(
  breach: CardTimelineBreach,
  formatMoney: (n: number) => string,
  formatMonth: (m: string) => string
): string {
  const legPhrases: Record<string, string> = {
    payments: 'a payment ran past everything reserved',
    residual: 'money came back beyond anything an envelope charged here',
    assignments: 'more money was moved back out of this envelope than it held',
    released: 'a refund released reserved cash',
    reservations: 'funded spending reserved',
  }
  const [leg] = breach.legs
  const cause = leg ? ` — ${legPhrases[leg.leg] ?? leg.leg} (${formatMoney(leg.amount)})` : ''
  return `Set aside first went below zero in ${formatMonth(breach.month)}, ${formatMoney(
    breach.set_aside_before
  )} → ${formatMoney(breach.set_aside_after)}${cause}.`
}

/**
 * Release: money out of a card's envelope, back to Ready to Assign or into
 * another envelope.
 *
 * Reuses the grid's Move money whole — same form, same endpoint, same audit
 * trail and undo. A card's envelope is an ordinary envelope to the server
 * (`_require_fundable` says so), so a second "take money off a card" path
 * would be a second implementation of a move, and the only thing genuinely
 * different here is what the user should be told before they do it.
 *
 * Offered on ANY card holding money, not only one with a surplus. The money
 * is committed to a bill, but committing it was a decision and so is taking
 * it back — needing that cash elsewhere this month is a real situation. Past
 * the spare it raises this card's Uncovered dollar for dollar, so the form
 * says that instead of refusing.
 */
function ReleaseButton({
  budgetId,
  month,
  card,
  envelope,
  formatMoney,
}: {
  budgetId: string
  month: string
  card: CardStatus
  /** The card's own envelope, looked up once for the whole strip rather than
   *  once per row — the popover's form fetches the list anyway, and React
   *  Query would only be deduplicating a query this component need not make
   *  N times. */
  envelope: Category
  formatMoney: (n: number) => string
}) {
  const isMobile = useIsMobile()
  const [open, setOpen] = useState(false)
  const anchorRef = useRef<HTMLButtonElement>(null)

  const { prefill, ceiling, lines } = releaseAnchors(card, formatMoney)
  const footnote = (
    <>
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </>
  )
  const label = `Release money from ${card.name}`

  return (
    <>
      <button
        type="button"
        ref={anchorRef}
        className="credit-cards__action"
        aria-label={label}
        onClick={() => setOpen(true)}
      >
        <ArrowRightLeft size={12} aria-hidden />
        Release
      </button>
      {open && !isMobile && (
        <MoveMoneyPopover
          budgetId={budgetId}
          month={month}
          category={envelope}
          available={card.set_aside}
          prefill={prefill}
          footnote={footnote}
          ceiling={ceiling}
          label={label}
          anchorRef={anchorRef}
          onClose={() => setOpen(false)}
        />
      )}
      {isMobile && (
        <BottomSheet
          open={open}
          onClose={() => setOpen(false)}
          historyKey={`release-${card.account_id}`}
        >
          <div className="credit-cards__release-sheet">
            <MoveMoneyForm
              budgetId={budgetId}
              month={month}
              category={envelope}
              available={card.set_aside}
              prefill={prefill}
              footnote={footnote}
              ceiling={ceiling}
              onClose={() => setOpen(false)}
            />
          </div>
        </BottomSheet>
      )}
    </>
  )
}

/**
 * One card, opened: what it owes and how much of that is covered, what is
 * going on in one sentence, and every action the card has — all in place,
 * under its line. Nothing here is a tooltip or a dialog; the old ⓘ door and
 * the "How credit cards work here" essay are what this replaces.
 */
function CardDetail({
  id,
  budgetId,
  month,
  card,
  toCategorize,
  assigned,
  needed,
  liabilityId,
  envelope,
  editing,
  draft,
  onDraft,
  onEdit,
  onCommit,
  onCancel,
  legsOpen,
  onLegs,
  onPeek,
  onPeekCategory,
  onTarget,
  formatMoney,
  formatMonth,
}: {
  id: string
  budgetId: string
  month: string
  card: CardStatus
  toCategorize: number
  assigned: number
  needed: number | null
  liabilityId: string | null
  envelope: Category | null
  editing: boolean
  draft: string
  onDraft: (value: string) => void
  onEdit: (value: string) => void
  onCommit: () => void
  onCancel: () => void
  legsOpen: boolean
  onLegs: () => void
  onPeek: () => void
  onPeekCategory: (categoryId: string, categoryName: string) => void
  onTarget: () => void
  formatMoney: (n: number) => string
  formatMonth: (m: string) => string
}) {
  const state = stateSentence(card, formatMoney)
  const drift = driftSentence(card, formatMoney)
  const movement = debtMovementLabel(card, formatMoney)
  const owed = Math.max(0, -card.balance)
  const covered = Math.min(owed, Math.max(0, card.set_aside))
  const tone = card.set_aside < 0 ? 'overspent' : state ? 'note' : 'calm'
  return (
    <div id={id} className="credit-cards__detail">
      <p className="credit-cards__key tabular">
        <span>
          Owes <strong>{formatMoney(owed)}</strong>
        </span>
        <span>{formatMoney(covered)} covered</span>
        <span>{formatMoney(card.uncovered)} not covered</span>
        {movement && <span className="credit-cards__movement">{movement} this month</span>}
      </p>
      <p className={`credit-cards__status credit-cards__status--${tone}`}>
        {state ? state.sentence : calmSentence(card, formatMoney)}
        {/* Absent wherever no action is honestly available: a row that must
          end in a suggestion will invent one. */}
        {state?.action && <strong className="credit-cards__status-action"> {state.action}</strong>}
      </p>
      {drift && <p className="credit-cards__status credit-cards__status--note">{drift}</p>}
      {/* What rode on this month, and from which envelopes. This lived in a
        dialog behind a second header chip ("of it on cards"); it is card
        debt, so it is said on the card, beside the assigned box that retires
        it. The ride is a month's net, not a set of rows, so each envelope
        opens its ordinary transactions rather than blaming particular ones. */}
      {card.overspent_this_month > 0 && (
        <p className="credit-cards__status credit-cards__status--note">
          {formatMoney(card.overspent_this_month)} of this month&rsquo;s overspending rode onto this
          card:{' '}
          {card.overspent_by_category.map((rode, i) => (
            <Fragment key={rode.category_id}>
              {i > 0 && ', '}
              <button
                type="button"
                className="credit-cards__inline-link"
                onClick={() => onPeekCategory(rode.category_id, rode.category_name)}
              >
                {rode.category_name}
              </button>{' '}
              <span className="tabular">{formatMoney(rode.amount)}</span>
            </Fragment>
          ))}
          .{' '}
          {/* The remedy, keyed on whether it works HERE: a shortfall shared
            across cards is handed out in a fixed order, so funding the
            envelope may shrink another card's ride first (F8). The server
            says which; this only reads it. */}
          {card.ride_reaches_this_card
            ? 'Cover Overspending retires it, or assign to this card below.'
            : 'Some of it rode onto another card too, and covering these envelopes reaches that card first. Assigning to this card below is certain to retire it.'}
        </p>
      )}
      {toCategorize > 0 && (
        <p className="credit-cards__status credit-cards__status--to-file">
          {toCategorize === 1
            ? '1 transaction on this card needs a category.'
            : `${toCategorize} transactions on this card need a category.`}{' '}
          Until then they only change what you owe. A refund filed to the envelope that made the
          purchase goes back to it; filed anywhere else, it turns this card red.{' '}
          <button type="button" className="credit-cards__inline-link" onClick={onPeek}>
            Show them
          </button>
        </p>
      )}
      <div className="credit-cards__assigned">
        <span className="credit-cards__assigned-label">Assigned this month</span>
        {card.category_id && editing ? (
          <input
            {...CELL_EDITOR_PROPS}
            className="credit-cards__assign"
            autoFocus
            inputMode="decimal"
            value={draft}
            aria-label={`Assigned to ${card.name} this month`}
            onChange={(e) => onDraft(e.target.value)}
            onBlur={onCommit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onCommit()
              if (e.key === 'Escape') onCancel()
            }}
          />
        ) : (
          <button
            type="button"
            className="credit-cards__assign-btn tabular"
            disabled={!card.category_id}
            aria-label={`Assigned to ${card.name} this month: ${formatMoney(assigned)}. Change it`}
            onClick={() => onEdit(assigned ? String(assigned) : '')}
          >
            {formatMoney(assigned)}
          </button>
        )}
        {needed !== null && needed > 0 && (
          <span className="credit-cards__hint">
            {formatMoney(needed)} more to reach the paydown target
          </span>
        )}
      </div>
      <div className="credit-cards__actions">
        <button type="button" className="credit-cards__action" onClick={onPeek}>
          Transactions
        </button>
        {/* Only where there is money to take: releasing from an empty
          envelope is a form with nothing to offer. */}
        {envelope && card.set_aside > 0 && (
          <ReleaseButton
            budgetId={budgetId}
            month={month}
            card={card}
            envelope={envelope}
            formatMoney={formatMoney}
          />
        )}
        {card.category_id && (
          <button type="button" className="credit-cards__action" onClick={onTarget}>
            <Crosshair size={12} aria-hidden />
            Paydown target
          </button>
        )}
        {liabilityId && (
          <Link to={`/liabilities/${liabilityId}`} className="credit-cards__action">
            <TrendingDown size={12} aria-hidden />
            Payoff projection
          </Link>
        )}
        <button
          type="button"
          className="credit-cards__action"
          aria-expanded={legsOpen}
          aria-label={`What makes up Set aside for ${card.name}`}
          onClick={onLegs}
        >
          {legsOpen ? (
            <ChevronDown size={12} aria-hidden />
          ) : (
            <ChevronRight size={12} aria-hidden />
          )}
          What makes up Set aside
        </button>
      </div>
      {legsOpen && (
        <ReserveLegs
          budgetId={budgetId}
          month={month}
          card={card}
          formatMoney={formatMoney}
          formatMonth={formatMonth}
        />
      )}
    </div>
  )
}

export function CreditCardsSection({ budgetId, month }: { budgetId: string; month: string }) {
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const setAssignment = useSetAssignment(budgetId)
  const { formatMoney, formatMonth } = useFormatters()
  const collapsed = useUIStore((s) => s.creditCardsCollapsed)
  const toggleCollapsed = useUIStore((s) => s.toggleCreditCardsCollapsed)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [peek, setPeek] = useState<PeekScope | null>(null)
  const [targetFor, setTargetFor] = useState<{ categoryId: string; name: string } | null>(null)
  const [legsFor, setLegsFor] = useState<string | null>(null)
  // Which card is open, by account — one at a time. Its detail is drawn in
  // place under its line, never in a dialog: the explanation used to live
  // behind an ⓘ button, and a reason you have to go looking for is one
  // nobody reads.
  const [openFor, setOpenFor] = useState<string | null>(null)
  const { data: liabilities = [] } = useLiabilities(budgetId)
  // Rows waiting for a category decide what a card's Set aside even is, so
  // the line says so. Served per account (`uncategorized_count`).
  const { data: accounts = [] } = useAccounts(budgetId)
  // For Release: the card's envelope is an ordinary category to the server,
  // and the move endpoint wants the category, not the account.
  const { data: categories = [] } = useCategories(budgetId)

  const cards = budgetMonth?.cards ?? []
  if (cards.length === 0) return null

  const balances = balancesByCategory(budgetMonth)
  // The server computes a card's envelope target verdict like any other
  // category's — the grid never draws the envelope, so this strip is where
  // the number surfaces.
  const totalUncovered = cards.reduce((sum, c) => sum + c.uncovered, 0)
  // This month's overspending that rode onto a card, read the way the
  // overspent chip reads its total (served, not re-added from the rows). It
  // sat in the header as an "of it on cards" chip with its own dialog; it is
  // card debt, so the cards band says it and each card names its envelopes.
  const rodeOn = overspending(budgetMonth).onCards
  // The payoff projection already exists on the Liability page — baseline
  // against the minimum payment versus the pace you are actually paying. The
  // strip never linked to it, so the one place that says "you are ahead" was
  // two navigations away from the place that says how much you owe.
  const liabilityByAccount = new Map(
    liabilities.filter((l) => l.linked_account_id).map((l) => [l.linked_account_id as string, l])
  )
  // A due date is a fact about NOW, and `card.balance` is the ledger through
  // the month being VIEWED. Pairing the two on a month in the past would put
  // a live "due in 4 days" beside a balance from 2024, so the indicator is
  // only offered from the current month on.
  const dueNoticesApply = month >= currentMonthStart()
  // Once, for every card: the header's line is an aggregate over the same
  // notices the rows draw, so the two cannot disagree about which bills are
  // close or how close the nearest one is.
  const asOf = today()
  const dueByAccount = new Map<string, DueNotice>()
  if (dueNoticesApply) {
    for (const c of cards) {
      const liability = liabilityByAccount.get(c.account_id)
      // `balance` is owed-NEGATIVE; dueSoonNotice takes owed as a positive.
      const notice = liability ? dueSoonNotice(liability, { today: asOf, owed: -c.balance }) : null
      if (notice) dueByAccount.set(c.account_id, notice)
    }
  }
  const headerDue = dueHeaderNote(
    cards
      .filter((c) => dueByAccount.has(c.account_id))
      .map((c) => ({ name: c.name, notice: dueByAccount.get(c.account_id) as DueNotice }))
  )

  const toCategorize = new Map(accounts.map((a) => [a.id, a.uncategorized_count ?? 0]))

  function commit(categoryId: string) {
    // The same rule the grid's cell uses: the box is the whole equation,
    // empty commits zero, negatives are allowed (money can come back off a
    // card), and only unparseable text writes nothing.
    const amount = parseAssignmentCommit(draft)
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
      /* The band stays put while its own cards scroll under it, and lets go
         at the section's end rather than following you into the categories.
         The fold control is the thing worth keeping reachable: with several
         cards expanded, collapsing meant scrolling back to the top to find
         the header you were trying to get rid of. */
      stickyHeader
      header={
        /* The whole band is the fold control, not just the caret: a header
           that reads as one thing should behave as one thing, and aiming at
           a 13px chevron is a needless ask. The button inside stays — it is
           what a keyboard focuses and what carries `aria-expanded` — but it
           no longer handles the click itself: activating it dispatches a
           click that bubbles here, so there is one handler rather than two
           that could disagree. */
        <div
          className="credit-cards__band"
          onClick={toggleCollapsed}
          data-testid="credit-cards-band"
        >
          <button
            type="button"
            className="credit-cards__header"
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
          <span className="credit-cards__summary">
            {cards.length === 1 ? '1 card' : `${cards.length} cards`}
            {totalUncovered !== 0 && <> · {formatMoney(totalUncovered)} not covered</>}
            {rodeOn > 0 && <> · {formatMoney(rodeOn)} rode on this month</>}
          </span>
          {/* Last, so it is the rightmost thing in the band: when the strip
            is collapsed this header is all there is, and a bill you cannot
            see coming is the one that catches you. */}
          {headerDue && (
            <span className="credit-cards__due credit-cards__due--header">
              <CalendarClock size={11} aria-hidden />
              {headerDue}
            </span>
          )}
        </div>
      }
    >
      {!collapsed && (
        <div id="credit-cards-body" className="credit-cards__body">
          <ul className="credit-cards__list" aria-label="Credit cards">
            {cards.map((card) => {
              const open = openFor === card.account_id
              const line = cardLine(card, toCategorize.get(card.account_id) ?? 0, formatMoney)
              const detailId = `credit-card-detail-${card.account_id}`
              const due = dueByAccount.get(card.account_id) ?? null
              return (
                <li className="credit-cards__card" key={card.account_id}>
                  {/* The whole line is the door: a word, a bar and the Set
                    aside pill say where the card stands, and tapping opens
                    the rest right here. Nothing interactive nests inside
                    it — the due chip is a label, not a control. */}
                  <button
                    type="button"
                    className={`credit-cards__line ${open ? 'credit-cards__line--open' : ''}`}
                    aria-expanded={open}
                    aria-controls={detailId}
                    onClick={() => setOpenFor(open ? null : card.account_id)}
                  >
                    <span className="credit-cards__line-name">
                      {open ? (
                        <ChevronDown size={12} aria-hidden />
                      ) : (
                        <ChevronRight size={12} aria-hidden />
                      )}
                      {line.mark && (
                        <span
                          className={`credit-cards__mark credit-cards__mark--${line.mark}`}
                          aria-hidden
                        />
                      )}
                      <span className="credit-cards__card-name">{card.name}</span>
                      <span
                        className={`credit-cards__word ${line.mark ? `credit-cards__word--${line.mark}` : ''}`}
                      >
                        {line.word}
                      </span>
                      {card.is_closed && <span className="credit-cards__closed-tag">Closed</span>}
                      {/* The bill is close and this card still owes something
                        — the one moment a due date is news rather than a
                        calendar fact. Never "overdue": the app cannot see
                        whether a statement was paid. */}
                      {due && (
                        <span className="credit-cards__due">
                          <CalendarClock size={11} aria-hidden />
                          Due {due.phrase}
                        </span>
                      )}
                    </span>
                    <span
                      className="credit-cards__bar"
                      role="img"
                      aria-label={`${Math.round(line.covered * 100)}% of what ${card.name} owes is set aside`}
                    >
                      <span style={{ width: `${line.covered * 100}%` }} />
                    </span>
                    <span className={`credit-cards__pill credit-cards__pill--${line.tone}`}>
                      {formatMoney(card.set_aside)}
                    </span>
                  </button>
                  {open && (
                    <CardDetail
                      id={detailId}
                      budgetId={budgetId}
                      month={month}
                      card={card}
                      toCategorize={toCategorize.get(card.account_id) ?? 0}
                      assigned={
                        card.category_id ? Number(balances.get(card.category_id)?.assigned ?? 0) : 0
                      }
                      needed={
                        card.category_id
                          ? (balances.get(card.category_id)?.needed_this_month ?? null)
                          : null
                      }
                      liabilityId={liabilityByAccount.get(card.account_id)?.id ?? null}
                      envelope={categories.find((c) => c.id === card.category_id) ?? null}
                      editing={editing === card.account_id}
                      draft={draft}
                      onDraft={setDraft}
                      onEdit={(value) => {
                        setDraft(value)
                        setEditing(card.account_id)
                      }}
                      onCommit={() => commit(card.category_id as string)}
                      onCancel={() => setEditing(null)}
                      legsOpen={legsFor === card.account_id}
                      onLegs={() =>
                        setLegsFor(legsFor === card.account_id ? null : card.account_id)
                      }
                      onPeek={() =>
                        setPeek({
                          kind: 'account',
                          accountId: card.account_id,
                          accountName: card.name,
                        })
                      }
                      onPeekCategory={(categoryId, categoryName) =>
                        setPeek({ kind: 'category', categoryId, categoryName })
                      }
                      onTarget={() =>
                        setTargetFor({ categoryId: card.category_id as string, name: card.name })
                      }
                      formatMoney={formatMoney}
                      formatMonth={formatMonth}
                    />
                  )}
                </li>
              )
            })}
          </ul>
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
        <TransactionsPeekModal budgetId={budgetId} scope={peek} onClose={() => setPeek(null)} />
      )}
    </Surface>
  )
}

/**
 * The grid's target editor, pointed at a card's envelope. A tiny
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
