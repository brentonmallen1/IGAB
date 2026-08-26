import { useState } from 'react'

/**
 * A list of names that may be long, shown as wrapping chips with the tail
 * folded behind "+N more". Twelve cards with no rate on record are twelve
 * chips, not one run-on sentence — and none of them is dropped.
 */
export function NameChips({
  names,
  limit = 6,
  label,
}: {
  names: string[]
  /** How many to show before folding the rest. */
  limit?: number
  /** Accessible label for the group. */
  label?: string
}) {
  const [open, setOpen] = useState(false)
  if (names.length === 0) return null
  const shown = open ? names : names.slice(0, limit)
  const hidden = names.length - shown.length
  return (
    <ul className="name-chips" aria-label={label}>
      {shown.map((name) => (
        <li key={name} className="name-chip">
          {name}
        </li>
      ))}
      {(hidden > 0 || open) && (
        <li className="name-chips__more">
          <button
            type="button"
            className="guide-link-button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
          >
            {open ? 'show fewer' : `+${hidden} more`}
          </button>
        </li>
      )}
    </ul>
  )
}
