import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, X } from 'lucide-react'
import { useAnchoredPosition } from '../../../hooks/useAnchoredPosition'
import {
  GroupedMultiSelect,
  type MultiSelectOption,
} from '../../common/GroupedMultiSelect/GroupedMultiSelect'
import './MultiSelectCombobox.css'

export type { MultiSelectOption }

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

/**
 * The report bar's filter control: a compact trigger, and the shared
 * GroupedMultiSelect hanging off it in an anchored dropdown. The list itself —
 * search, bulk actions, tri-state groups — lives in common/ so the planner's
 * import dialog and this filter cannot drift apart.
 */
export function MultiSelectCombobox({
  selectedIds,
  options,
  onChange,
  placeholder = 'All',
  label,
  disabled = false,
  title,
}: Props) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // 220 is this filter's floor: the trigger is narrow in the report bar but
  // the option labels (account and category names) are not.
  const dropdownPos = useAnchoredPosition(triggerRef, open, {
    width: 'trigger',
    minWidth: 220,
  })

  function measureAndOpen() {
    if (disabled) return
    setOpen(true)
  }

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      const t = e.target as Node
      if (!triggerRef.current?.contains(t) && !listRef.current?.contains(t)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  const count = selectedIds.length
  const displayLabel =
    count === 0
      ? placeholder
      : count === 1
        ? (options.find((o) => o.id === selectedIds[0])?.label ?? '1 selected')
        : `${count} selected`

  const dropdown =
    open && dropdownPos
      ? createPortal(
          <div
            ref={listRef}
            className="msc__dropdown"
            style={{
              position: 'fixed',
              top: dropdownPos.top,
              bottom: dropdownPos.bottom,
              left: dropdownPos.left,
              width: dropdownPos.width,
              maxHeight: dropdownPos.maxHeight,
              zIndex: 'var(--z-dropdown)',
              // The panel does not scroll; its list does. 40px is the search
              // row, which stays put above it.
              ['--scroll-list-max' as string]:
                typeof dropdownPos.maxHeight === 'number'
                  ? `${Math.max(dropdownPos.maxHeight - 40, 80)}px`
                  : '280px',
            }}
          >
            <GroupedMultiSelect
              options={options}
              selectedIds={selectedIds}
              onChange={onChange}
              onEscape={() => setOpen(false)}
              autoFocusSearch
            />
          </div>,
          document.body
        )
      : null

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
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') measureAndOpen()
        }}
      >
        <span className="msc__value">{displayLabel}</span>
        {count > 0 && (
          <button
            className="msc__remove"
            onMouseDown={(e) => {
              e.stopPropagation()
              e.preventDefault()
              onChange([])
            }}
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
