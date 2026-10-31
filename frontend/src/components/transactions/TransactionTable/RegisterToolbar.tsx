import { Banknote, Plus } from 'lucide-react'
import { TransactionSearch } from '../TransactionSearch/TransactionSearch'
import { SearchHelp } from '../TransactionSearch/SearchHelp'
import type { RegisterToggle } from './registerToggles'
import './TransactionTable.css'

interface Props {
  searchQuery: string
  onSearchChange: (q: string) => void
  onAdd: () => void
  /** From `registerPayAction` — null on registers that take no payment. */
  pay: { label: string; onClick: () => void } | null
  /** How the rows are drawn (`registerToggles`). Empty where the toggles live
   *  elsewhere — the phone account page's Tools sheet, which leaves this row to
   *  the search box. */
  toggles: RegisterToggle[]
}

/** The register's top row: search, how the rows are drawn, and the actions
 *  done to this account. */
export function RegisterToolbar({ searchQuery, onSearchChange, onAdd, pay, toggles }: Props) {
  return (
    <div className="transaction-table__toolbar">
      {/* The ⓘ sits beside the box, not inside it: inside, it shared an edge
          with the clear ✕ and took the click meant for it. */}
      <div className="transaction-table__search-group">
        <TransactionSearch value={searchQuery} onChange={onSearchChange} />
        <span className="transaction-table__search-help">
          <SearchHelp />
        </span>
      </div>
      {/* A toggle, so its name stays put and aria-pressed carries the state;
          the tooltip says what a click will do. On the phone account page
          these move into Tools; the all-accounts register has no such sheet,
          so they stay here there. */}
      {toggles.map(({ id, noun, icon: Icon, show, onChange }) => (
        <button
          key={id}
          type="button"
          className="transaction-table__toggle-btn"
          aria-pressed={show}
          aria-label={`Show ${noun}`}
          title={show ? `Hide ${noun}` : `Show ${noun}`}
          onClick={() => onChange(!show)}
        >
          <Icon size={14} aria-hidden />
        </button>
      ))}
      {pay && (
        <button type="button" className="transaction-table__pay-btn" onClick={pay.onClick}>
          <Banknote size={14} />
          {pay.label}
        </button>
      )}
      <button className="transaction-table__add-btn" onClick={onAdd}>
        <Plus size={14} />
        Add Transaction
      </button>
    </div>
  )
}
