import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import './InlineInput.css'

interface Props {
  value: string
  onCommit: (value: string) => void
  onCancel?: () => void
  placeholder?: string
  type?: 'text' | 'currency'
  className?: string
  disabled?: boolean
  autoFocus?: boolean
}

export function InlineInput({
  value,
  onCommit,
  onCancel,
  placeholder = '',
  type = 'text',
  className = '',
  disabled = false,
  autoFocus = true,
}: Props) {
  const [draft, setDraft] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [autoFocus])

  function commit() {
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
      setDraft(value)
      onCancel?.()
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
    />
  )
}
