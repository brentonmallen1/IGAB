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
  /** Draw each split's lines under it (uiStore `showSplitLines`). */
  showSplitLines: boolean
  onShowSplitLinesChange: (show: boolean) => void
}

/** The register's top row: search, how the rows are drawn, and the actions
 *  done to this account. */
export function RegisterToolbar({
  searchQuery,
  onSearchChange,
  onAdd,
  pay,
  showSplitLines,
  onShowSplitLinesChange,
}: Props) {
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
          the tooltip says what a click will do. Kept on phones too: the
          register toolbar has no overflow menu to fold it into, and the
          button is one icon wide. */}
      <button
        type="button"
        className="transaction-table__toggle-btn"
        aria-pressed={showSplitLines}
        aria-label="Show split lines"
        title={showSplitLines ? 'Hide split lines' : 'Show split lines'}
        onClick={() => onShowSplitLinesChange(!showSplitLines)}
      >
        <ListTree size={14} aria-hidden />
      </button>
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
