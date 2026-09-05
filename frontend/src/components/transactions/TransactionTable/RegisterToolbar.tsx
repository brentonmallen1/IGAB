import { Banknote, Plus } from 'lucide-react'
import { TransactionSearch } from '../TransactionSearch/TransactionSearch'
import { SearchHelp } from '../TransactionSearch/SearchHelp'
import './TransactionTable.css'

interface Props {
  searchQuery: string
  onSearchChange: (q: string) => void
  onAdd: () => void
  /** From `registerPayAction` — null on registers that take no payment. */
  pay: { label: string; onClick: () => void } | null
}

/** The register's top row: search, and the actions done to this account. */
export function RegisterToolbar({ searchQuery, onSearchChange, onAdd, pay }: Props) {
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
