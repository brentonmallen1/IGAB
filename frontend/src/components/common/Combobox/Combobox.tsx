import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, Plus } from 'lucide-react'
import './Combobox.css'

export interface ComboboxOption {
  id: string
  label: string
  group?: string
}

interface Props {
  value: string | null
  options: ComboboxOption[]
  onChange: (id: string | null) => void
  onCreateNew?: (query: string) => Promise<ComboboxOption> | void
  placeholder?: string
  disabled?: boolean
  className?: string
  autoFocus?: boolean
  onBlurClose?: () => void
}

interface DropdownPos {
  top: number
  left: number
  width: number
}

export function Combobox({
  value,
  options,
  onChange,
  onCreateNew,
  placeholder = 'Search…',
  disabled = false,
  className = '',
  autoFocus = false,
  onBlurClose,
}: Props) {
  const selectedOption = value ? options.find((o) => o.id === value) : null
  // When auto-focused (inline edit), start with empty query so all options are visible.
  // The selected option is still highlighted in the list via CSS.
  const [query, setQuery] = useState(autoFocus ? '' : (selectedOption?.label ?? ''))
  const [open, setOpen] = useState(autoFocus)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const [dropdownPos, setDropdownPos] = useState<DropdownPos | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const triggerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const filtered = options.filter((o) =>
    o.label.toLowerCase().includes(query.toLowerCase())
  )

  const grouped = filtered.reduce<{ group: string; items: ComboboxOption[] }[]>((acc, opt) => {
    const g = opt.group ?? ''
    const existing = acc.find((a) => a.group === g)
    if (existing) {
      existing.items.push(opt)
    } else {
      acc.push({ group: g, items: [opt] })
    }
    return acc
  }, [])

  const showCreate = onCreateNew && query.trim() && !filtered.some(
    (o) => o.label.toLowerCase() === query.toLowerCase()
  )
  const totalItems = filtered.length + (showCreate ? 1 : 0)

  function measureAndOpen() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (rect) {
      setDropdownPos({
        top: rect.bottom + 2,
        left: rect.left,
        width: rect.width,
      })
    }
    setOpen(true)
    setHighlightedIndex(0)
  }

  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus()
      inputRef.current?.select()
      measureAndOpen()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFocus])

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      const target = e.target as Node
      const inTrigger = triggerRef.current?.contains(target)
      const inList = listRef.current?.contains(target)
      if (!inTrigger && !inList) {
        setOpen(false)
        onBlurClose?.()
      }
    }
    function handleScroll() {
      // Reposition on scroll
      const rect = triggerRef.current?.getBoundingClientRect()
      if (rect) {
        setDropdownPos({ top: rect.bottom + 2, left: rect.left, width: rect.width })
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClick)
      window.addEventListener('scroll', handleScroll, true)
      return () => {
        document.removeEventListener('mousedown', handleClick)
        window.removeEventListener('scroll', handleScroll, true)
      }
    }
  }, [open, onBlurClose])

  // Scroll highlighted item into view
  useEffect(() => {
    const item = listRef.current?.children[highlightedIndex] as HTMLElement | undefined
    item?.scrollIntoView({ block: 'nearest' })
  }, [highlightedIndex])

  const selectOption = useCallback(
    (opt: ComboboxOption) => {
      onChange(opt.id)
      setQuery(opt.label)
      setOpen(false)
      onBlurClose?.()
    },
    [onChange, onBlurClose]
  )

  const handleCreateNew = useCallback(async () => {
    if (!onCreateNew || !query.trim()) return
    const result = await onCreateNew(query.trim())
    if (result) {
      onChange(result.id)
      setQuery(result.label)
    }
    setOpen(false)
    onBlurClose?.()
  }, [onCreateNew, query, onChange, onBlurClose])

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        measureAndOpen()
      }
      return
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightedIndex((i) => Math.min(i + 1, totalItems - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightedIndex((i) => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (highlightedIndex < filtered.length) {
          selectOption(filtered[highlightedIndex])
        } else if (showCreate) {
          handleCreateNew()
        }
        break
      case 'Escape':
        setOpen(false)
        setQuery(selectedOption?.label ?? '')
        onBlurClose?.()
        break
      case 'Tab':
        setOpen(false)
        onBlurClose?.()
        break
    }
  }

  function handleInputChange(v: string) {
    setQuery(v)
    if (!open) measureAndOpen()
    setHighlightedIndex(0)
    if (!v) onChange(null)
  }

  const dropdown = open && dropdownPos ? createPortal(
    <ul
      ref={listRef}
      className="combobox__list"
      role="listbox"
      style={{
        position: 'fixed',
        top: dropdownPos.top,
        left: dropdownPos.left,
        width: dropdownPos.width,
        zIndex: 9999,
      }}
    >
      {grouped.length === 0 && !showCreate && (
        <li className="combobox__empty">No results</li>
      )}

      {grouped.map(({ group, items }) => (
        <li key={group || '__ungrouped'} className="combobox__group">
          {group && <div className="combobox__group-header">{group}</div>}
          <ul>
            {items.map((opt) => {
              const idx = filtered.indexOf(opt)
              return (
                <li
                  key={opt.id}
                  className={`combobox__option ${idx === highlightedIndex ? 'combobox__option--highlighted' : ''} ${opt.id === value ? 'combobox__option--selected' : ''}`}
                  onMouseDown={(e) => { e.preventDefault(); selectOption(opt) }}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                  role="option"
                  aria-selected={opt.id === value}
                >
                  {opt.label}
                </li>
              )
            })}
          </ul>
        </li>
      ))}

      {showCreate && (
        <li
          className={`combobox__option combobox__option--create ${filtered.length === highlightedIndex ? 'combobox__option--highlighted' : ''}`}
          onMouseDown={(e) => { e.preventDefault(); handleCreateNew() }}
          onMouseEnter={() => setHighlightedIndex(filtered.length)}
          role="option"
        >
          <Plus size={12} />
          <span>Create &ldquo;{query}&rdquo;</span>
        </li>
      )}
    </ul>,
    document.body
  ) : null

  return (
    <div ref={triggerRef} className={`combobox ${className} ${open ? 'combobox--open' : ''}`}>
      <div className="combobox__trigger">
        <input
          ref={inputRef}
          className="combobox__input"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          onFocus={measureAndOpen}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
        />
        <span className="combobox__arrow">
          <ChevronDown size={12} />
        </span>
      </div>

      {dropdown}
    </div>
  )
}
