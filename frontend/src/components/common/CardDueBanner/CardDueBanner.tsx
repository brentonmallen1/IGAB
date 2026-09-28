import { CalendarClock, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAccounts } from '../../../api/accounts'
import { useCardDueDismissals, useDismissCardDue } from '../../../api/cardDueDismissals'
import { useLiabilities } from '../../../api/liabilities'
import { useFormatters } from '../../../hooks/useFormatters'
import { useAppStore } from '../../../stores/appStore'
import { today } from '../../../utils/dates'
import { reminderWords } from '../../../utils/paymentDue'
import { Surface } from '../Surface'
import { bannerLines } from './bannerLines'
import './CardDueBanner.css'

/**
 * A card bill that is due or past due, on every page, until a payment lands
 * or somebody dismisses it.
 *
 * The rule is `reminderForCard` (utils/paymentDue.ts), the same one the
 * credit-cards strip and the terms header read. This adds only the part
 * that is the banner's own: dismissing. A dismissal is stored on the server
 * (`api/cardDueDismissals.ts`), so the household's other device stops
 * showing it too, and it is of one due date in one state — a "due" dismissed
 * this week does not hide the "past due" that follows if nothing is paid.
 *
 * In the flow of the shell's content column, between the header and the
 * page — never fixed. A fixed bar is anchored to the layout viewport, which
 * iOS slides out from under the visible area when the keyboard opens; in
 * flow it takes its row and the page scroller starts below it.
 */
export function CardDueBanner() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: dismissals = [] } = useCardDueDismissals(budgetId)
  const dismiss = useDismissCardDue(budgetId)
  const { formatMoney, formatDayMonth } = useFormatters()

  const lines = bannerLines(liabilities, accounts, dismissals, today())
  if (lines.length === 0) return null

  return (
    <Surface as="section" variant="chrome" className="card-due-banner" aria-label="Card bills">
      <ul className="card-due-banner__list">
        {lines.map(({ accountId, name, owed, reminder }) => {
          const past = reminder.state === 'past_due'
          return (
            <li
              key={accountId}
              className={`card-due-banner__line ${past ? 'card-due-banner__line--past-due' : ''}`}
            >
              <CalendarClock size={14} aria-hidden className="card-due-banner__icon" />
              <span className="card-due-banner__text">
                <Link className="card-due-banner__card" to={`/accounts/${accountId}`}>
                  {name}
                </Link>{' '}
                is{' '}
                <span className="card-due-banner__state">
                  {reminderWords(reminder, formatDayMonth)}
                </span>
                {!past && reminder.days > 1 && <> ({formatDayMonth(reminder.dueDate)})</>}
                <span className="card-due-banner__detail">
                  {' · '}
                  {formatMoney(owed)} owed
                  {/* The claim rests on the ledger: a payment whose checking
                    leg never paired as a transfer is invisible here, so say
                    what was seen rather than that nothing was paid. Not "no
                    payment since" the bill before: a payment after it may
                    have been spent on an older bill, and was still seen. */}
                  {past &&
                    (reminder.lastPayment ? (
                      <> · Last payment seen {formatDayMonth(reminder.lastPayment)}</>
                    ) : (
                      <> · No payment seen since {formatDayMonth(reminder.watchedFrom)}</>
                    ))}
                </span>
              </span>
              <button
                type="button"
                className="card-due-banner__dismiss"
                aria-label={`Dismiss the reminder for ${name}`}
                disabled={dismiss.isPending}
                onClick={() => dismiss.mutate({ accountId, reminder })}
              >
                <X size={14} aria-hidden />
              </button>
            </li>
          )
        })}
      </ul>
    </Surface>
  )
}
