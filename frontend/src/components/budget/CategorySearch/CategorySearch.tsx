import { useRef } from 'react'
import { Search, X } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import './CategorySearch.css'

interface Props {
  /** Where the field sits and how wide it is — the caller's layout. */
  className?: string
  autoFocus?: boolean
  /** After Escape has cleared the query. Without one, Escape also blurs. */
  onEscape?: () => void
}

/**
 * The budget grid's category search: name, group, or `tag:`.
 *
 * Drawn in the desktop filter bar and in the phone's column header row. It was
 * written twice — the bar's and the Tools sheet's — with different
 * placeholders, and only the bar's cleared on Escape.
 */
export function CategorySearch({ className = '', autoFocus = false, onEscape }: Props) {
  const value = useUIStore((s) => s.categorySearch)
  const setValue = useUIStore((s) => s.setCategorySearch)
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div className={`category-search ${value ? 'has-value' : ''} ${className}`.trim()}>
      <Search size={13} className="category-search__icon" aria-hidden="true" />
      <input
        ref={inputRef}
        className="category-search__input"
        type="search"
        enterKeyHint="search"
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            setValue('')
            if (onEscape) onEscape()
            else inputRef.current?.blur()
          } else if (e.key === 'Enter') {
            // The filter is already applied; Enter only puts the keyboard away.
            inputRef.current?.blur()
          }
        }}
        placeholder="Filter… or tag:essential"
        aria-label="Filter categories by name, group, or tag"
      />
      {value && (
        <button
          type="button"
          className="category-search__clear"
          onClick={() => {
            setValue('')
            inputRef.current?.focus()
          }}
          aria-label="Clear the filter"
          title="Clear the filter"
        >
          <X size={12} />
        </button>
      )}
    </div>
  )
}
