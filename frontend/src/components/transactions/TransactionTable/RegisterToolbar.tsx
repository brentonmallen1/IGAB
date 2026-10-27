import { Banknote, ListTree, Plus } from 'lucide-react'
import { TransactionSearch } from '../TransactionSearch/TransactionSearch'
import { SearchHelp } from '../TransactionSearch/SearchHelp'
import './TransactionTable.css'

interface Props {
  searchQuery: string
  onSearchChange: (q: string) => void
  onAdd: () => void
  /** From `registerPayAction` — null on registers that take no payment. */
  pay: { label: string; onClick: () => void } | null
  /** Draw each split's lines under it (uiStore `showSplitLines`). Null where
   *  the toggle lives elsewhere — the phone account page's Tools sheet, which
   *  leaves this row to the search box. */
  splitLines: { show: boolean; onChange: (show: boolean) => void } | null
}

/** The register's top row: search, how the rows are drawn, and the actions
 *  done to this account. */
export function RegisterToolbar({ searchQuery, onSearchChange, onAdd, pay, splitLines }: Props) {
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
          the tooltip says what a click will do. On the phone account page it
          moves into Tools; the all-accounts register has no such sheet, so it
          stays here there. */}
      {splitLines && (
        <button
          type="button"
          className="transaction-table__toggle-btn"
          aria-pressed={splitLines.show}
          aria-label="Show split lines"
          title={splitLines.show ? 'Hide split lines' : 'Show split lines'}
          onClick={() => splitLines.onChange(!splitLines.show)}
        >
          <ListTree size={14} aria-hidden />
        </button>
      )}
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
