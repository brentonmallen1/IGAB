import { useState, useRef, useEffect, startTransition } from 'react'
import { Search, X } from 'lucide-react'
import { matchSuggestions } from '../../../utils/searchParser'
import { SearchHelp } from './SearchHelp'
import './TransactionSearch.css'

const DEBOUNCE_MS = 150

interface Props {
  value: string
  onChange: (query: string) => void
  placeholder?: string
}

export function TransactionSearch({ value, onChange, placeholder = 'Search transactions…' }: Props) {
  const [localValue, setLocalValue] = useState(value)
  const [focused, setFocused] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync when parent clears the value externally
  useEffect(() => {
    setLocalValue(value)
  }, [value])

  // Matching lives in searchParser alongside the list itself, so the palette
  // offers exactly the same vocabulary this box does.
  const activeSuggestions = matchSuggestions(localValue)
  const shouldShowSuggestions = focused && showSuggestions &&
    (localValue.length === 0 || activeSuggestions.length > 0)

  // Reset active index when suggestion list changes
  useEffect(() => { setActiveIndex(-1) }, [activeSuggestions.length])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function propagate(v: string, immediate = false) {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    if (immediate) {
      startTransition(() => onChange(v))
    } else {
      debounceTimer.current = setTimeout(() => startTransition(() => onChange(v)), DEBOUNCE_MS)
    }
  }

  function handleChange(v: string) {
    setLocalValue(v)
    setShowSuggestions(true)
    setActiveIndex(-1)
    propagate(v)
  }

  function appendSuggestion(syntax: string, matchedLen: number) {
    // Replace the matched trailing portion of the input with the full syntax.
    // Trailing spaces are trimmed first so `matchedLen` (measured against the
    // trimmed tokens) lines up with what is being cut.
    const trimmedValue = localValue.trimEnd()
    const prefix = trimmedValue.slice(0, trimmedValue.length - matchedLen)
    const next = prefix + syntax
    setLocalValue(next)
    propagate(next, true)
    inputRef.current?.focus()
    setShowSuggestions(false)
    setActiveIndex(-1)
  }

  function handleClear() {
    // Deliberately NOT refocusing the input: X means "done searching". The
    // old refocus made clearing act like clicking into the field — the
    // suggestions panel popped open (and on mobile the keyboard re-raised),
    // which read as the search refusing to close.
    setLocalValue('')
    propagate('', true)
    setShowSuggestions(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (shouldShowSuggestions && activeSuggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIndex((i) => (i + 1) % activeSuggestions.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((i) => (i <= 0 ? activeSuggestions.length - 1 : i - 1))
        return
      }
      if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault()
        const s = activeSuggestions[activeIndex]
        appendSuggestion(s.syntax, s.matchedLen)
        return
      }
      if (e.key === 'Tab' && activeIndex >= 0) {
        e.preventDefault()
        const s = activeSuggestions[activeIndex]
        appendSuggestion(s.syntax, s.matchedLen)
        return
      }
    }

    if (e.key === 'Escape') {
      if (localValue) {
        setLocalValue('')
        propagate('', true)
      } else {
        setShowSuggestions(false)
        inputRef.current?.blur()
      }
    }
  }

  return (
    <div ref={containerRef} className={`txn-search ${focused ? 'txn-search--focused' : ''}`}>
      <span className="txn-search__icon"><Search size={13} /></span>
      <input
        ref={inputRef}
        className="txn-search__input"
        value={localValue}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => { setFocused(true); setShowSuggestions(true) }}
        onBlur={() => setFocused(false)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
      />
      {localValue && (
        <button className="txn-search__clear" onClick={handleClear} aria-label="Clear search">
          <X size={12} />
        </button>
      )}
      {/* Inside the box, so the explanation sits where the question occurs.
          The dropdown below completes syntax for someone who already knows a
          language is there; this is what tells them there is one. */}
      <span className="txn-search__help">
        <SearchHelp />
      </span>

      {shouldShowSuggestions && (
        <div className="txn-search__suggestions">
          <div className="txn-search__suggestions-header">Search syntax</div>
          {activeSuggestions.map((s, i) => (
            <button
              key={s.syntax}
              ref={i === activeIndex ? (el) => el?.scrollIntoView({ block: 'nearest' }) : undefined}
              className={`txn-search__suggestion ${i === activeIndex ? 'txn-search__suggestion--active' : ''}`}
              onMouseDown={(e) => { e.preventDefault(); appendSuggestion(s.syntax, s.matchedLen) }}
              onMouseEnter={() => setActiveIndex(i)}
            >
              <code className="txn-search__syntax">{s.syntax}</code>
              <span className="txn-search__desc">{s.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
