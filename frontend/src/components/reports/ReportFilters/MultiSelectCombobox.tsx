import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, X, Check } from 'lucide-react'
import './MultiSelectCombobox.css'

export interface MultiSelectOption {
  id: string
  label: string
  group?: string
}

interface Props {
  selectedIds: string[]
  options: MultiSelectOption[]
  onChange: (ids: string[]) => void
  placeholder?: string
  label?: string
  /** Dimmed and inert — used when the active report ignores this filter */
  disabled?: boolean
  title?: string
}

interface DropdownPos {
  top: number
  left: number
  width: number
}

export function MultiSelectCombobox({ selectedIds, options, onChange, placeholder = 'All', label, disabled = false, title }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [dropdownPos, setDropdownPos] = useState<DropdownPos | null>(null)
  const triggerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [highlightedIndex, setHighlightedIndex] = useState(0)

  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes(query.toLowerCase())
  )

  const grouped = filtered.reduce<{ group: string; items: MultiSelectOption[] }[]>((acc, opt) => {
    const g = opt.group ?? ''
    const existing = acc.find((a) => a.group === g)
    if (existing) existing.items.push(opt)
    else acc.push({ group: g, items: [opt] })
    return acc
  }, [])

  const flatFiltered = grouped.flatMap((g) => g.items)

  function measureAndOpen() {
    if (disabled) return
    const rect = triggerRef.current?.getBoundingClientRect()
    if (rect) setDropdownPos({ top: rect.bottom + 2, left: rect.left, width: Math.max(rect.width, 220) })
    setOpen(true)
    setHighlightedIndex(0)
  }

  function close() {
    setOpen(false)
    setQuery('')
  }

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      const t = e.target as Node
      if (!triggerRef.current?.contains(t) && !listRef.current?.contains(t)) close()
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  function toggle(id: string) {
    if (selectedIds.includes(id)) onChange(selectedIds.filter((x) => x !== id))
    else onChange([...selectedIds, id])
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open) { if (e.key === 'ArrowDown' || e.key === 'Enter') measureAndOpen(); return }
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); setHighlightedIndex((i) => Math.min(i + 1, flatFiltered.length - 1)); break
      case 'ArrowUp': e.preventDefault(); setHighlightedIndex((i) => Math.max(i - 1, 0)); break
      case 'Enter': e.preventDefault(); if (flatFiltered[highlightedIndex]) toggle(flatFiltered[highlightedIndex].id); break
      case 'Escape': close(); break
    }
  }

  const count = selectedIds.length
  const displayLabel = count === 0 ? placeholder : count === 1
    ? (options.find((o) => o.id === selectedIds[0])?.label ?? '1 selected')
    : `${count} selected`

  const dropdown = open && dropdownPos ? createPortal(
    <div
      ref={listRef}
      className="msc__dropdown"
      style={{ position: 'fixed', top: dropdownPos.top, left: dropdownPos.left, width: dropdownPos.width, zIndex: 'var(--z-dropdown)' }}
    >
      <div className="msc__search-wrap">
        <input
          ref={inputRef}
          className="msc__search"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setHighlightedIndex(0) }}
          onKeyDown={handleKeyDown}
          placeholder="Search…"
          autoFocus
        />
        <div className="msc__actions">
          {options.length > 0 && selectedIds.length < options.length && (
            <button className="msc__action-btn" onMouseDown={(e) => { e.preventDefault(); onChange(options.map(o => o.id)) }} type="button">
              Select all
            </button>
          )}
          {count > 0 && (
            <button className="msc__action-btn" onMouseDown={(e) => { e.preventDefault(); onChange([]) }} type="button">
              Clear all
            </button>
          )}
        </div>
      </div>
      {filtered.length === 0 && <div className="msc__empty">No results</div>}
      {grouped.map(({ group, items }) => {
        const groupItemIds = items.map(o => o.id)
        const allGroupSelected = groupItemIds.length > 0 && groupItemIds.every(id => selectedIds.includes(id))
        const someGroupSelected = groupItemIds.some(id => selectedIds.includes(id)) && !allGroupSelected
        function toggleGroup(e: React.MouseEvent) {
          e.preventDefault()
          if (allGroupSelected) {
            onChange(selectedIds.filter(id => !groupItemIds.includes(id)))
          } else {
            onChange([...new Set([...selectedIds, ...groupItemIds])])
          }
        }
        return (
          <div key={group || '__ungrouped'} className="msc__group">
            {group && (
              <div
                className={`msc__group-header msc__group-header--clickable ${allGroupSelected ? 'msc__group-header--selected' : ''} ${someGroupSelected ? 'msc__group-header--partial' : ''}`}
                onMouseDown={toggleGroup}
              >
                <span className="msc__group-check">
                  {allGroupSelected && <Check size={10} />}
                  {someGroupSelected && <span className="msc__group-partial-dash">—</span>}
                </span>
                {group}
              </div>
            )}
            {items.map((opt) => {
              const idx = flatFiltered.indexOf(opt)
              const checked = selectedIds.includes(opt.id)
              return (
                <div
                  key={opt.id}
                  className={`msc__option ${idx === highlightedIndex ? 'msc__option--highlighted' : ''} ${checked ? 'msc__option--checked' : ''}`}
                  onMouseDown={(e) => { e.preventDefault(); toggle(opt.id) }}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                >
                  <span className="msc__check">{checked && <Check size={11} />}</span>
                  <span className="msc__option-label">{opt.label}</span>
                </div>
              )
            })}
          </div>
        )
      })}
    </div>,
    document.body
  ) : null

  return (
    <div className={`msc ${disabled ? 'msc--disabled' : ''}`} title={disabled ? title : undefined}>
      {label && <span className="msc__label">{label}</span>}
      <div
        ref={triggerRef}
        className={`msc__trigger ${open ? 'msc__trigger--open' : ''} ${count > 0 ? 'msc__trigger--active' : ''}`}
        onClick={measureAndOpen}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label={label ?? placeholder}
        aria-haspopup="listbox"
        aria-expanded={open}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') measureAndOpen() }}
      >
        <span className="msc__value">{displayLabel}</span>
        {count > 0 && (
          <button
            className="msc__remove"
            onMouseDown={(e) => { e.stopPropagation(); e.preventDefault(); onChange([]) }}
            type="button"
            aria-label="Clear"
          >
            <X size={11} />
          </button>
        )}
        <ChevronDown size={12} className="msc__arrow" />
      </div>
      {dropdown}
    </div>
  )
}
