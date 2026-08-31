import { useMemo } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { describeSearchChips, removeSearchChip } from '../../../utils/searchParser'
import './SearchFilterChips.css'

interface Props {
  query: string
  /** The same maps the register hands the parser. A chip can only be honest
   *  about `category:`/`payee:`/`account:` if it knows whether they resolved,
   *  and passing only a size is what forced the chips to guess. Pass an empty
   *  accountMap off the all-accounts register, exactly as the parser is given. */
  categoryMap: Map<string, string>
  payeeMap: Map<string, string>
  accountMap: Map<string, string>
  onChange: (query: string) => void
}

/** Removable chips for each recognised filter in the search query. */
export function SearchFilterChips({ query, categoryMap, payeeMap, accountMap, onChange }: Props) {
  const chips = useMemo(
    () => describeSearchChips(query, categoryMap, payeeMap, accountMap),
    [query, categoryMap, payeeMap, accountMap]
  )
  if (chips.length === 0) return null

  return (
    <div className="search-chips" role="list" aria-label="Active search filters">
      {chips.map((chip) => (
        <span
          key={chip.key}
          className={
            'search-chips__chip' + (chip.unrecognized ? ' search-chips__chip--unrecognized' : '')
          }
          role="listitem"
          title={
            chip.unrecognized
              ? 'This part of the search was ignored, so these results are not filtered by it.'
              : undefined
          }
        >
          {chip.unrecognized && <AlertTriangle size={11} aria-hidden />}
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
