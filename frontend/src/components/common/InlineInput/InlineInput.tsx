import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import './InlineInput.css'

interface Props {
  value: string
  onCommit: (value: string) => void
  onCancel?: () => void
  /** Tab / Shift+Tab: commit, then let the caller move editing on (the
   *  register's cells unmount on commit, so native Tab would land nowhere). */
  onTabOut?: (direction: 1 | -1) => void
  placeholder?: string
  type?: 'text' | 'currency'
  className?: string
  disabled?: boolean
  autoFocus?: boolean
  'aria-label'?: string
}

export function InlineInput({
  value,
  onCommit,
  onCancel,
  onTabOut,
  placeholder = '',
  type = 'text',
  className = '',
  disabled = false,
  autoFocus = true,
  'aria-label': ariaLabel,
}: Props) {
  const [draft, setDraft] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)
  // A commit ends this input's life (the caller unmounts it); a blur that
  // fires on the way out must not commit the same value a second time.
  const settled = useRef(false)

  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [autoFocus])

  function commit() {
    if (settled.current) return
    settled.current = true
    const trimmed = draft.trim()
    if (trimmed !== value) onCommit(trimmed)
    else onCancel?.()
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      settled.current = true
      setDraft(value)
      onCancel?.()
    } else if (e.key === 'Tab' && onTabOut) {
      e.preventDefault()
      commit()
      onTabOut(e.shiftKey ? -1 : 1)
    }
  }

  return (
    <input
      ref={inputRef}
      className={`inline-input ${className}`}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      disabled={disabled}
      inputMode={type === 'currency' ? 'decimal' : 'text'}
      autoComplete="off"
      aria-label={ariaLabel}
    />
  )
}
