import { useMemo, useState } from 'react'
import { Check, Plus, Search } from 'lucide-react'
import { BottomSheet } from '../BottomSheet/BottomSheet'
import type { ComboboxOption } from '../Combobox/Combobox'
import './SelectionSheet.css'

export interface SelectionSheetOption extends ComboboxOption {
  /** Small right-aligned hint, e.g. a distance ("~120 m") */
  hint?: string
}

interface Props {
  open: boolean
  onClose: () => void
  title: string
  options: SelectionSheetOption[]
  value: string | null
  onChange: (id: string | null) => void
  onCreateNew?: (query: string) => Promise<ComboboxOption | void> | void
  /** Pinned group rendered above the full list (e.g. "Nearby" payees) */
  topSection?: { label: string; options: SelectionSheetOption[] }
  placeholder?: string
  /** Adds an explicit "None" row that selects null (e.g. "No category") */
  allowNone?: boolean
  noneLabel?: string
}

/**
 * Mobile replacement for the Combobox dropdown: a full-height sheet with a
 * sticky search field and large grouped rows. The keyboard never occludes the
 * input because it anchors to the top.
 */
export function SelectionSheet({
  open,
  onClose,
  title,
  options,
  value,
  onChange,
  onCreateNew,
  topSection,
  placeholder = 'Search…',
  allowNone = false,
  noneLabel = 'None',
}: Props) {
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((o) => o.label.toLowerCase().includes(q))
  }, [options, query])

  const grouped = useMemo(() => {
    const groups = new Map<string, SelectionSheetOption[]>()
    for (const o of filtered) {
      const key = o.group ?? ''
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(o)
    }
    return Array.from(groups.entries())
  }, [filtered])

  const exactMatch = filtered.some((o) => o.label.toLowerCase() === query.trim().toLowerCase())
  const showCreate = !!onCreateNew && query.trim().length > 0 && !exactMatch

  function pick(id: string | null) {
    onChange(id)
    setQuery('')
    onClose()
  }

  async function handleCreate() {
    if (!onCreateNew || creating) return
    setCreating(true)
    try {
      const created = await onCreateNew(query.trim())
      if (created) pick(created.id)
      else {
        setQuery('')
        onClose()
      }
    } finally {
      setCreating(false)
    }
  }

  function renderOption(o: SelectionSheetOption) {
    return (
      <button key={o.id} className="selection-sheet__option" onClick={() => pick(o.id)}>
        <span className="selection-sheet__option-label">{o.label}</span>
        {o.hint && <span className="selection-sheet__option-hint">{o.hint}</span>}
        {o.id === value && <Check size={16} className="selection-sheet__check" />}
      </button>
    )
  }

  return (
    <BottomSheet open={open} onClose={onClose} title={title} height="full" historyKey={`select-${title}`}>
      <div className="selection-sheet">
        <div className="selection-sheet__search">
          <Search size={16} aria-hidden />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            aria-label={placeholder}
          />
        </div>

        <div className="selection-sheet__list">
          {showCreate && (
            <button
              className="selection-sheet__option selection-sheet__option--create"
              onClick={handleCreate}
              disabled={creating}
            >
              <Plus size={16} />
              <span>{creating ? 'Creating…' : `Create "${query.trim()}"`}</span>
            </button>
          )}

          {allowNone && !query && (
            <button className="selection-sheet__option" onClick={() => pick(null)}>
              <span className="selection-sheet__option-label selection-sheet__option-label--muted">
                {noneLabel}
              </span>
              {value === null && <Check size={16} className="selection-sheet__check" />}
            </button>
          )}

          {topSection && topSection.options.length > 0 && !query && (
            <>
              <div className="selection-sheet__group-label">{topSection.label}</div>
              {topSection.options.map(renderOption)}
            </>
          )}

          {grouped.map(([group, opts]) => (
            <div key={group || '__ungrouped__'}>
              {group && <div className="selection-sheet__group-label">{group}</div>}
              {opts.map(renderOption)}
            </div>
          ))}

          {filtered.length === 0 && !showCreate && (
            <div className="selection-sheet__empty">No matches</div>
          )}
        </div>
      </div>
    </BottomSheet>
  )
}
