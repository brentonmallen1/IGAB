import { useState, useRef, useEffect, useCallback, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, Plus } from 'lucide-react'
import { useAnchoredPosition } from '../../../hooks/useAnchoredPosition'
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
  /** Tab / Shift+Tab: the caller moves editing to its next/previous field
   *  itself (the register's cells unmount on commit, so native Tab would
   *  land on <body>). Without it, Tab lets focus move natively. Either way
   *  a highlighted option the user typed or arrowed to is selected first. */
  onTabOut?: (direction: 1 | -1) => void
  'aria-label'?: string
  'aria-labelledby'?: string
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
  onTabOut,
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
}: Props) {
  const selectedOption = value ? options.find((o) => o.id === value) : null
  const [query, setQuery] = useState(autoFocus ? '' : (selectedOption?.label ?? ''))
  const [open, setOpen] = useState(autoFocus)

  // Sync the text when the selection changes from outside (e.g. an AI
  // suggestion or autofill setting the value) — but never while the user is
  // actively typing in the open dropdown
  const [lastValue, setLastValue] = useState(value)
  if (value !== lastValue) {
    setLastValue(value)
    if (!open) setQuery(selectedOption?.label ?? '')
  }
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const triggerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const dropdownPos = useAnchoredPosition(triggerRef, open, { width: 'trigger' })

  const filtered = options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))

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
    setOpen(true)
    setHighlightedIndex(0)
    engaged.current = false
  }

  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus()
      inputRef.current?.select()
      // No measureAndOpen() here any more: `open` already initialises to
      // autoFocus and the highlight to 0, so all this call did was take the
      // measurement that useAnchoredPosition now takes for itself.
    }
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
    if (open) {
      document.addEventListener('mousedown', handleClick)
      return () => document.removeEventListener('mousedown', handleClick)
    }
  }, [open, onBlurClose])

  // Only keyboard navigation (and typing, which resets to the top) may scroll
  // the list to follow the highlight. Hover also moves the highlight, and if
  // hover scrolled too, an option half-hidden at the list's edge would scroll
  // into view, slide the next option under a stationary pointer, and creep
  // the whole list — which is what made reaching the Split button "weird".
  const highlightSource = useRef<'keyboard' | 'pointer'>('keyboard')
  // Has the user typed or arrowed since the list opened? Only then does Tab
  // take the highlight: the list opens on focus with the first option
  // highlighted, and someone tabbing straight through a row must not be
  // handed its first payee.
  const engaged = useRef(false)

  // Scroll highlighted item into view within the list (manual to avoid page scroll side-effects)
  useEffect(() => {
    if (highlightSource.current !== 'keyboard') return
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
    const tabDirection: 1 | -1 = e.shiftKey ? -1 : 1
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        measureAndOpen()
      } else if (e.key === 'Tab' && onTabOut) {
        e.preventDefault()
        onTabOut(tabDirection)
      }
      return
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        highlightSource.current = 'keyboard'
        engaged.current = true
        setHighlightedIndex((i) => Math.min(i + 1, filtered.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        highlightSource.current = 'keyboard'
        engaged.current = true
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
      case 'Tab': {
        // Tab used to close the list and throw the highlight away — the one
        // key on the register that discarded what the user had just found.
        const picked =
          engaged.current && highlightedIndex < filtered.length ? filtered[highlightedIndex] : null
        setOpen(false)
        if (picked) {
          onChange(picked.id)
          setQuery(picked.label)
        }
        if (onTabOut) {
          e.preventDefault()
          onTabOut(tabDirection)
        } else {
          onBlurClose?.()
        }
        break
      }
    }
  }

  function handleInputChange(v: string) {
    setQuery(v)
    if (!open) measureAndOpen()
    highlightSource.current = 'keyboard'
    engaged.current = true
    setHighlightedIndex(0)
    if (!v) onChange(null)
  }

  const dropdown =
    open && dropdownPos
      ? createPortal(
          <div
            ref={dropdownRef}
            className="combobox__dropdown"
            style={{
              position: 'fixed',
              top: dropdownPos.top,
              bottom: dropdownPos.bottom,
              left: dropdownPos.left,
              width: dropdownPos.width,
              maxHeight: dropdownPos.maxHeight,
              zIndex: 'var(--z-dropdown)',
            }}
          >
            {onCreateNew && (
              <div className="combobox__dropdown-header">
                <button
                  className="combobox__create-btn"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    handleCreateNew()
                  }}
                  type="button"
                >
                  <Plus size={12} />
                  {query.trim() ? `Create "${query}"` : createLabel}
                </button>
              </div>
            )}

            <ul ref={listRef} className="combobox__list" role="listbox">
              {grouped.length === 0 && <li className="combobox__empty">No results</li>}

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
                          onMouseDown={(e) => {
                            e.preventDefault()
                            selectOption(opt)
                          }}
                          onMouseEnter={() => {
                            highlightSource.current = 'pointer'
                            setHighlightedIndex(idx)
                          }}
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

            {footerSlot && <div className="combobox__dropdown-footer">{footerSlot}</div>}
          </div>,
          document.body
        )
      : null

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
