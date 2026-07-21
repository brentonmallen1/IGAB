import { useState, useRef, useEffect, useCallback, type KeyboardEvent, type ReactNode } from 'react'
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
  onCreateNew?: (query: string) => Promise<ComboboxOption | void> | void
  createLabel?: string
  footerSlot?: ReactNode
  placeholder?: string
  disabled?: boolean
  className?: string
  autoFocus?: boolean
  onBlurClose?: () => void
  'aria-label'?: string
  'aria-labelledby'?: string
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
  createLabel = 'New…',
  footerSlot,
  placeholder = 'Search…',
  disabled = false,
  className = '',
  autoFocus = false,
  onBlurClose,
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
}: Props) {
  const selectedOption = value ? options.find((o) => o.id === value) : null
  const [query, setQuery] = useState(autoFocus ? '' : (selectedOption?.label ?? ''))
  const [open, setOpen] = useState(autoFocus)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const [dropdownPos, setDropdownPos] = useState<DropdownPos | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const triggerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      const target = e.target as Node
      const inTrigger = triggerRef.current?.contains(target)
      const inDropdown = dropdownRef.current?.contains(target)
      if (!inTrigger && !inDropdown) {
        setOpen(false)
        onBlurClose?.()
      }
    }
    function handleScroll(e: Event) {
      // Ignore scroll events from within the dropdown list itself to prevent jumpiness
      if (dropdownRef.current?.contains(e.target as Node)) return
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

  // Scroll highlighted item into view within the list (manual to avoid page scroll side-effects)
  useEffect(() => {
    const list = listRef.current
    const item = list?.querySelector<HTMLElement>(`[data-option-index="${highlightedIndex}"]`)
    if (!list || !item) return
    const itemTop = item.offsetTop
    const itemBottom = itemTop + item.offsetHeight
    const listTop = list.scrollTop
    const listBottom = listTop + list.clientHeight
    if (itemTop < listTop) {
      list.scrollTop = itemTop
    } else if (itemBottom > listBottom) {
      list.scrollTop = itemBottom - list.clientHeight
    }
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
    if (!onCreateNew || !query.trim()) {
      inputRef.current?.focus()
      return
    }
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
        setHighlightedIndex((i) => Math.min(i + 1, filtered.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightedIndex((i) => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (highlightedIndex < filtered.length) {
          selectOption(filtered[highlightedIndex])
        } else if (onCreateNew && query.trim()) {
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
    <div
      ref={dropdownRef}
      className="combobox__dropdown"
      style={{
        position: 'fixed',
        top: dropdownPos.top,
        left: dropdownPos.left,
        width: dropdownPos.width,
        zIndex: 9999,
      }}
    >
      {onCreateNew && (
        <div className="combobox__dropdown-header">
          <button
            className="combobox__create-btn"
            onMouseDown={(e) => { e.preventDefault(); handleCreateNew() }}
            type="button"
          >
            <Plus size={12} />
            {query.trim() ? `Create "${query}"` : createLabel}
          </button>
        </div>
      )}

      <ul
        ref={listRef}
        className="combobox__list"
        role="listbox"
      >
        {grouped.length === 0 && (
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
                    data-option-index={idx}
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
      </ul>

      {footerSlot && (
        <div className="combobox__dropdown-footer">
          {footerSlot}
        </div>
      )}
    </div>,
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
          role="combobox"
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-autocomplete="list"
          aria-label={ariaLabel}
          aria-labelledby={ariaLabelledby}
        />
        <span className="combobox__arrow">
          <ChevronDown size={12} />
        </span>
      </div>

      {dropdown}
    </div>
  )
}
