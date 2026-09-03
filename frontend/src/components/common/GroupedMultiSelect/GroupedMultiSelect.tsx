import { useId, useState, type KeyboardEvent } from 'react'
import { Check } from 'lucide-react'
import './GroupedMultiSelect.css'

export interface MultiSelectOption {
  id: string
  label: string
  /** Options carrying the same group render under one clickable header. */
  group?: string
}

interface Props {
  options: MultiSelectOption[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  autoFocusSearch?: boolean
  searchPlaceholder?: string
  emptyText?: string
  /** "N selected" beside the bulk actions. */
  showCount?: boolean
  /** Escape while the search has focus — the host decides what closes. */
  onEscape?: () => void
  className?: string
}

/**
 * The searchable, grouped, multi-select list — search box, bulk actions,
 * tri-state group headers, checkable rows.
 *
 * Host-agnostic on purpose: it has no trigger and no positioning, so the
 * report bar can hang it off an anchored dropdown while the category planner
 * puts the same list in a Dialog. Picking several things out of a grouped set
 * is one rule; it gets one implementation.
 *
 * The list is a `.scroll-list`; hosts tune `--scroll-list-max` on it.
 */
export function GroupedMultiSelect({
  options,
  selectedIds,
  onChange,
  autoFocusSearch = false,
  searchPlaceholder = 'Search…',
  emptyText = 'No results',
  showCount = true,
  onEscape,
  className,
}: Props) {
  const [query, setQuery] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const listId = useId()

  const filtered = options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))

  const grouped = filtered.reduce<{ group: string; items: MultiSelectOption[] }[]>((acc, opt) => {
    const g = opt.group ?? ''
    const existing = acc.find((a) => a.group === g)
    if (existing) existing.items.push(opt)
    else acc.push({ group: g, items: [opt] })
    return acc
  }, [])

  const flatFiltered = grouped.flatMap((g) => g.items)
  const count = selectedIds.length

  function toggle(id: string) {
    if (selectedIds.includes(id)) onChange(selectedIds.filter((x) => x !== id))
    else onChange([...selectedIds, id])
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightedIndex((i) => Math.min(i + 1, flatFiltered.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightedIndex((i) => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (flatFiltered[highlightedIndex]) toggle(flatFiltered[highlightedIndex].id)
        break
      case 'Escape':
        onEscape?.()
        break
    }
  }

  const highlighted = flatFiltered[highlightedIndex]

  return (
    <div className={['gms', className].filter(Boolean).join(' ')}>
      <div className="gms__search-wrap">
        <input
          className="gms__search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setHighlightedIndex(0)
          }}
          onKeyDown={handleKeyDown}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          aria-controls={listId}
          aria-activedescendant={highlighted ? `${listId}-${highlighted.id}` : undefined}
          autoFocus={autoFocusSearch}
        />
        <div className="gms__actions">
          {showCount && count > 0 && <span className="gms__count">{count} selected</span>}
          {options.length > 0 && count < options.length && (
            <button
              className="gms__action-btn"
              onMouseDown={(e) => {
                e.preventDefault()
                onChange(options.map((o) => o.id))
              }}
              type="button"
            >
              Select all
            </button>
          )}
          {count > 0 && (
            <button
              className="gms__action-btn"
              onMouseDown={(e) => {
                e.preventDefault()
                onChange([])
              }}
              type="button"
            >
              Clear all
            </button>
          )}
        </div>
      </div>
      <div className="gms__list scroll-list" id={listId} role="listbox" aria-multiselectable>
        {filtered.length === 0 && <div className="gms__empty">{emptyText}</div>}
        {grouped.map(({ group, items }) => {
          const groupItemIds = items.map((o) => o.id)
          const allGroupSelected =
            groupItemIds.length > 0 && groupItemIds.every((id) => selectedIds.includes(id))
          const someGroupSelected =
            groupItemIds.some((id) => selectedIds.includes(id)) && !allGroupSelected
          function toggleGroup(e: React.MouseEvent) {
            e.preventDefault()
            if (allGroupSelected) {
              onChange(selectedIds.filter((id) => !groupItemIds.includes(id)))
            } else {
              onChange([...new Set([...selectedIds, ...groupItemIds])])
            }
          }
          return (
            <div key={group || '__ungrouped'} className="gms__group">
              {group && (
                <button
                  type="button"
                  className={`gms__group-header ${allGroupSelected ? 'gms__group-header--selected' : ''} ${someGroupSelected ? 'gms__group-header--partial' : ''}`}
                  onMouseDown={toggleGroup}
                  aria-pressed={allGroupSelected}
                >
                  <span className="gms__group-check">
                    {allGroupSelected && <Check size={10} />}
                    {someGroupSelected && <span className="gms__group-partial-dash">—</span>}
                  </span>
                  <span className="gms__group-name">{group}</span>
                  <span className="gms__group-tally">
                    {groupItemIds.filter((id) => selectedIds.includes(id)).length}/
                    {groupItemIds.length}
                  </span>
                </button>
              )}
              {items.map((opt) => {
                const idx = flatFiltered.indexOf(opt)
                const checked = selectedIds.includes(opt.id)
                return (
                  <div
                    key={opt.id}
                    id={`${listId}-${opt.id}`}
                    role="option"
                    aria-selected={checked}
                    className={`gms__option ${idx === highlightedIndex ? 'gms__option--highlighted' : ''} ${checked ? 'gms__option--checked' : ''}`}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      toggle(opt.id)
                    }}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                  >
                    <span className="gms__check">{checked && <Check size={11} />}</span>
                    <span className="gms__option-label">{opt.label}</span>
                  </div>
                )
              })}
            </div>
          )
        })}
      </div>
    </div>
  )
}
