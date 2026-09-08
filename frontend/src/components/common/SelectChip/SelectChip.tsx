import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useRef } from 'react'
import { ChevronDown } from 'lucide-react'
import './SelectChip.css'

export interface SelectChipOption {
  value: string
  label: string
}

export interface SelectChipGroup {
  /** Empty renders the options bare, with no `<optgroup>`. */
  label: string
  options: SelectChipOption[]
}

interface Props {
  value: string
  onChange: (value: string) => void
  groups: SelectChipGroup[]
  /** The option for the empty value, and what the chip reads when nothing is
   *  chosen. */
  placeholder: string
  icon?: LucideIcon
  /** Accent treatment — the chip is carrying a choice, not sitting at rest. */
  active?: boolean
  title: string
  ariaLabel: string
  /** Drawn inside the chip after the label. Pointer events are off across the
   *  whole face, so this is for markers, never controls. */
  children?: ReactNode
  className?: string
}

/**
 * A chip whose whole face is a native `<select>`.
 *
 * Two of these existed in the budget bar — the view control and the "N more"
 * filter picker — as separate markup with the same four tricks in each: the
 * select stretched invisibly over the chip so its padding and icons are not
 * dead to the pointer, `:has(...:focus-visible)` moving the ring to the chip
 * so the select's own outline does not draw a stray box inside it, and the
 * blur-on-pointer dance below. The pair had already drifted: only one of them
 * carried an icon, and only one showed which value was chosen.
 *
 * Native rather than a custom menu, so keyboard and screen-reader behaviour
 * and the mobile wheel come for free.
 */
export function SelectChip({
  value,
  onChange,
  groups,
  placeholder,
  icon: Icon,
  active = false,
  title,
  ariaLabel,
  children,
  className = '',
}: Props) {
  // A select keeps focus after a click and browsers count that as
  // focus-visible, so the ring lingered after the user was plainly finished.
  // Only drop focus for pointer use — keyboard users change the value with
  // arrow keys and must keep it.
  const viaPointer = useRef(false)

  const chosen = groups.flatMap((g) => g.options).find((o) => o.value === value)
  const label = chosen?.label ?? placeholder

  return (
    <span className={`select-chip ${active ? 'active' : ''} ${className}`.trim()}>
      {Icon && <Icon size={12} className="select-chip__icon" />}
      <span className="select-chip__label" title={label}>
        {label}
      </span>
      {children}
      <ChevronDown size={12} className="select-chip__caret" />
      <select
        className="select-chip__select"
        value={value}
        onPointerDown={() => {
          viaPointer.current = true
        }}
        onKeyDown={() => {
          viaPointer.current = false
        }}
        onChange={(e) => {
          onChange(e.target.value)
          if (viaPointer.current) e.currentTarget.blur()
        }}
        title={title}
        aria-label={ariaLabel}
      >
        <option value="">{placeholder}</option>
        {groups.map((group, i) =>
          group.options.length === 0 ? null : group.label ? (
            <optgroup key={group.label} label={group.label}>
              {group.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </optgroup>
          ) : (
            group.options.map((o) => (
              <option key={`${i}-${o.value}`} value={o.value}>
                {o.label}
              </option>
            ))
          )
        )}
      </select>
    </span>
  )
}
