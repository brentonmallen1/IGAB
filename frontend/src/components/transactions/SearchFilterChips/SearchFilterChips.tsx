import { useMemo } from 'react'
import { X } from 'lucide-react'
import { describeSearchChips, removeSearchChip } from '../../../utils/searchParser'
import './SearchFilterChips.css'

interface Props {
  query: string
  /** Pass the account map size only on the all-accounts register, where
   * account: tokens resolve; 0 elsewhere (mirrors the parser). */
  accountMapSize: number
  onChange: (query: string) => void
}

/** Removable chips for each recognised filter in the search query. */
export function SearchFilterChips({ query, accountMapSize, onChange }: Props) {
  const chips = useMemo(() => describeSearchChips(query, accountMapSize), [query, accountMapSize])
  if (chips.length === 0) return null

  return (
    <div className="search-chips" role="list" aria-label="Active search filters">
      {chips.map((chip) => (
        <span key={chip.key} className="search-chips__chip" role="listitem">
          {chip.label}
          <button
            className="search-chips__remove"
            onClick={() => onChange(removeSearchChip(query, chip))}
            aria-label={`Remove filter: ${chip.label}`}
          >
            <X size={11} />
          </button>
        </span>
      ))}
    </div>
  )
}
