import { Link } from 'react-router-dom'
import { useGuideOverview } from '../../api/guide'
import { useIncomeSplitReport } from '../../api/reports'
import { useAppStore } from '../../stores/appStore'
import { lastMonthsWindow } from '../../utils/dateWindow'
import { RULE, gapPhrase, shares, tooUnfiled } from '../../utils/incomeSplit'
import { IncomeSplitBar } from '../reports/IncomeSplitBar'
import './IncomeSplitNote.css'

/** The window the note reads: the last three complete months, the Essentials
 *  headline's own — whatever range the report was last left on. */
const WINDOW_MONTHS = 3

/**
 * The household's own split on the roadmap node that teaches the 50/30/20
 * rule: the report's bar, and what each gap points to.
 *
 * A reading, never a grade. No light, no checkup finding, no colour for
 * "over" — where you live decides a lot of the needs figure, and a heuristic
 * that turned red at 58% would be telling a household in an expensive city
 * it was failing. What is useful is which gap there is, because each points
 * somewhere different: needs to the slow levers, wants to the quick one,
 * saving to the next steps on this very roadmap.
 *
 * Shown only with personalization on, like every figure the Guide reads
 * from the budget.
 */
export function IncomeSplitNote() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  const personal = overview?.preferences.personalization ?? false
  const window = lastMonthsWindow(WINDOW_MONTHS)
  const { data } = useIncomeSplitReport(personal ? budgetId : null, window.start, window.end)
  if (!personal || !data) return null

  if (!data.tagged) {
    return (
      <div className="income-split-note">
        <p className="income-split-note__line">
          Tag the categories you couldn’t go without as Essential and your own split shows here.
        </p>
      </div>
    )
  }

  const pct = shares(data)
  if (!pct) return null
  const unfiled = tooUnfiled(data)

  const rows = [
    {
      key: 'needs',
      label: 'Needs',
      share: pct.needs,
      rule: RULE.needs,
      says:
        pct.needs > RULE.needs
          ? 'Needs move slowly. Housing, the car and insurance are decided once and paid every month, so this changes at a lease renewal or a refinance, not by trimming.'
          : 'Room under the rule here is what makes the other two possible.',
    },
    {
      key: 'wants',
      label: 'Wants',
      share: pct.wants,
      rule: RULE.wants,
      says:
        pct.wants > RULE.wants
          ? 'This is the lever that moves month to month.'
          : 'Room you have already made.',
    },
    {
      key: 'savings',
      label: 'Saving',
      share: pct.savings,
      rule: RULE.savings,
      says:
        pct.savings < RULE.savings
          ? 'The next steps on this roadmap are where that goes: a starter emergency fund, then high-interest debt.'
          : 'At or past the rule — the later steps on this roadmap are where it can go next.',
    },
  ] as const

  return (
    <div className="income-split-note income-split-palette">
      <div className="income-split-note__head">
        <span>Yours, the last three complete months</span>
        <Link to="/reports?tab=income-split">Open Income Split</Link>
      </div>
      <IncomeSplitBar data={data} compact />
      {unfiled ? (
        <p className="income-split-note__line">
          {pct.uncategorized}% went out unfiled, so these shares can still move a lot. File those
          first.
        </p>
      ) : (
        <ul className="income-split-note__rows">
          {rows.map((r) => (
            <li key={r.key}>
              <span className={`income-split-note__swatch income-split-note__swatch--${r.key}`} />
              <strong>
                {r.label} {r.share}% · {gapPhrase(r.share, r.rule)}
              </strong>
              <span>{r.says}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
