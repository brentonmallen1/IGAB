import { useState, useRef, useEffect } from 'react'
import { Search, X } from 'lucide-react'
import { SEARCH_SUGGESTIONS } from '../../../utils/searchParser'
import './TransactionSearch.css'

interface Props {
  value: string
  onChange: (query: string) => void
  placeholder?: string
}

export function TransactionSearch({ value, onChange, placeholder = 'Search transactions…' }: Props) {
  const [focused, setFocused] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Show suggestions on empty input when focused
  const shouldShowSuggestions = focused && showSuggestions && value.length === 0

  // Show autocomplete for partial "is:" etc.
  const activeSuggestions = SEARCH_SUGGESTIONS.filter(
    (s) => !value || s.syntax.startsWith(value.split(' ').at(-1) ?? '')
  )

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function handleChange(v: string) {
    onChange(v)
    setShowSuggestions(true)
  }

  function appendSuggestion(syntax: string) {
    const parts = value.split(' ')
    parts[parts.length - 1] = syntax
    onChange(parts.join(' '))
    inputRef.current?.focus()
    setShowSuggestions(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      if (value) onChange('')
      else { setShowSuggestions(false); inputRef.current?.blur() }
    }
  }

  return (
    <div ref={containerRef} className={`txn-search ${focused ? 'txn-search--focused' : ''}`}>
      <span className="txn-search__icon"><Search size={13} /></span>
      <input
        ref={inputRef}
        className="txn-search__input"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => { setFocused(true); setShowSuggestions(true) }}
        onBlur={() => setFocused(false)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
      />
      {value && (
        <button className="txn-search__clear" onClick={() => { onChange(''); inputRef.current?.focus() }}>
          <X size={12} />
        </button>
      )}

      {(shouldShowSuggestions || (focused && value && activeSuggestions.length > 0)) && (
        <div className="txn-search__suggestions">
          <div className="txn-search__suggestions-header">Search syntax</div>
          {activeSuggestions.map((s) => (
            <button
              key={s.syntax}
              className="txn-search__suggestion"
              onMouseDown={(e) => { e.preventDefault(); appendSuggestion(s.syntax) }}
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
