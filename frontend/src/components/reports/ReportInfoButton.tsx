import { useState, useRef, useEffect } from 'react'
import { Info, X } from 'lucide-react'
import './ReportInfoButton.css'

interface Props {
  title: string
  children: React.ReactNode
}

export function ReportInfoButton({ title, children }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="report-info" ref={ref}>
      <button
        className="report-info__btn"
        onClick={() => setOpen((v) => !v)}
        type="button"
        aria-label="Report information"
      >
        <Info size={15} />
      </button>
      {open && (
        <div className="report-info__panel">
          <div className="report-info__header">
            <span className="report-info__title">{title}</span>
            <button className="report-info__close" onClick={() => setOpen(false)} type="button">
              <X size={13} />
            </button>
          </div>
          <div className="report-info__body">{children}</div>
        </div>
      )}
    </div>
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
