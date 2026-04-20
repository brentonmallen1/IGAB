import { useRef, useEffect } from 'react'
import './DatePicker.css'

interface Props {
  value: string
  onChange: (date: string) => void
  onClose?: () => void
  disabled?: boolean
  className?: string
}

export function DatePicker({ value, onChange, onClose, disabled = false, className = '' }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.showPicker?.()
  }, [])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.value) {
      onChange(e.target.value)
      onClose?.()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose?.()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (inputRef.current?.value) {
        onChange(inputRef.current.value)
        onClose?.()
      }
    }
  }

  return (
    <input
      ref={inputRef}
      type="date"
      className={`date-picker ${className}`}
      value={value}
      onChange={handleChange}
      onBlur={onClose}
      onKeyDown={handleKeyDown}
      disabled={disabled}
    />
  )
}
