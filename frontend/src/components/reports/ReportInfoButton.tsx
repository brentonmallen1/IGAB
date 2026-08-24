import { InfoPopover } from '../common/InfoPopover/InfoPopover'
import './ReportInfoButton.css'

interface Props {
  title: string
  children: React.ReactNode
}

/**
 * An ⓘ button beside a report's title.
 *
 * A thin naming layer over the shared InfoPopover so every "how does this
 * work?" in the app behaves the same way; the scope notes below are what
 * makes this one report-specific.
 */
export function ReportInfoButton({ title, children }: Props) {
  return (
    <InfoPopover title={title} label={`About the ${title} report`}>
      {children}
    </InfoPopover>
  )
}

export type ReportScope =
  | 'all-accounts'
  | 'on-budget'
  | 'on-budget-filterable'
  | 'categories'
  | 'cash-projection'
  | 'liabilities'
  | 'overview'

const SCOPE_COPY: Record<ReportScope, string> = {
  'all-accounts': 'Accounts: every account counts — on-budget, tracking, and loans.',
  'on-budget':
    'Accounts: on-budget only. Plain activity inside tracking accounts ' +
    '(investments, loans) never appears here — categorized transfers to them do.',
  'on-budget-filterable':
    'Accounts: on-budget by default — plain activity inside tracking accounts ' +
    "doesn't count, categorized transfers to them do. Picking accounts in the " +
    'filter bar overrides this, tracking accounts included.',
  categories:
    'Accounts: follows categories, not accounts — anything categorized counts, '
    + "matching the budget page's envelope math.",
  'cash-projection': 'Accounts: open, on-budget accounts only.',
  liabilities:
    'Accounts: driven by your tracked liabilities, not account types — add a ' +
    'liability (or link one to a loan account) to include a debt here.',
  overview:
    'Accounts: net worth spans every account; the income, spending, and burn ' +
    'metrics count on-budget accounts only.',
}

/** One standard line in every report's info panel stating which accounts the
 * report considers — the scoping is deliberate and should never be a
 * surprise the user has to reverse-engineer from the numbers. */
export function ReportScopeNote({ scope }: { scope: ReportScope }) {
  return <p className="report-info__scope">{SCOPE_COPY[scope]}</p>
}

/** Stated on every report that now means spending in the narrow sense. Moving
 *  money to a tracked account used to count as spending here — it no longer
 *  does, and a number that changed under the user deserves saying so out
 *  loud rather than being noticed later and distrusted. */
export function SpendingClassNote() {
  return (
    <p className="report-info__scope">
      Counts spending only. Money moved into savings or investments, or used to
      pay down a tracked debt, leaves your budget but stays yours — so it is not
      counted here. Open any transaction to see how it is classified and why.
    </p>
  )
}
