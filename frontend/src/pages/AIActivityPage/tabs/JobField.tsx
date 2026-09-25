import { useState, type ReactNode } from 'react'
import { Combobox, type ComboboxOption } from '../../../components/common/Combobox/Combobox'

/**
 * One field of where a scan's row landed (its account, its category), named
 * on every row and changeable while the row waits for approval.
 *
 * The chip, the button that opens a picker, and the picker that closes on
 * pick or blur are one control. JobAccount and JobCategory both render it,
 * so the two fields look and behave the same.
 */
export function JobField({
  icon,
  name,
  title,
  editTitle,
  editable,
  value,
  options,
  placeholder,
  pickerLabel,
  onPick,
}: {
  icon: ReactNode
  /** What the chip reads. */
  name: string
  /** Tooltip while it only reads out. */
  title: string
  /** Tooltip on the button that opens the picker. */
  editTitle: string
  /** Offer the picker. The caller decides; a row that is not waiting never is. */
  editable: boolean
  value: string | null
  options: ComboboxOption[]
  placeholder: string
  pickerLabel: string
  /** A choice different from `value`. Picking the current value is no change. */
  onPick: (id: string) => void
}) {
  const [picking, setPicking] = useState(false)

  if (picking && editable) {
    return (
      <span className="ai-activity__field ai-activity__field--picking">
        <Combobox
          value={value}
          options={options}
          onChange={(id) => {
            setPicking(false)
            if (id && id !== value) onPick(id)
          }}
          placeholder={placeholder}
          aria-label={pickerLabel}
          autoFocus
          onBlurClose={() => setPicking(false)}
        />
      </span>
    )
  }

  if (!editable) {
    return (
      <span className="ai-activity__field" title={title}>
        {icon}
        {name}
      </span>
    )
  }

  return (
    <button
      className="ai-activity__field ai-activity__field--button"
      onClick={() => setPicking(true)}
      title={editTitle}
    >
      {icon}
      {name}
    </button>
  )
}
