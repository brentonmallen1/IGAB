import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Combobox, type ComboboxOption } from '../Combobox/Combobox'
import { SelectionSheet, type SelectionSheetSection } from '../SelectionSheet/SelectionSheet'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import './PickerField.css'

const NONE = '__none__'

interface Props {
  value: string | null
  onChange: (id: string | null) => void
  /** Grouped by `group`; each group draws the house header. */
  options: ComboboxOption[]
  /** A shortlist above the full list (e.g. Recent accounts). On a phone it is
   *  the sheet's pinned section, hidden while searching; on desktop it is the
   *  first group of the dropdown. */
  pinned?: SelectionSheetSection
  /** Offer an explicit "none" choice that selects null */
  allowNone?: boolean
  /** The None row's label, and what an empty field reads on a phone. */
  noneLabel?: string
  /** The desktop input's placeholder. Defaults to `noneLabel`. */
  placeholder?: string
  sheetTitle: string
  /** The phone sheet's search placeholder. */
  searchPlaceholder?: string
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

/**
 * A searchable, theme-aware picker in place of a native <select>: a Combobox
 * dropdown on desktop, a full-height SelectionSheet on a phone (native
 * pickers there are unsearchable and unthemed). Both draw the options'
 * groups under the house `.combobox__group-header` / sheet group label.
 *
 * The category and account pickers are both this; each only builds its
 * options.
 */
export function PickerField({
  value,
  onChange,
  options,
  pinned,
  allowNone = false,
  noneLabel = 'None',
  placeholder,
  sheetTitle,
  searchPlaceholder,
  disabled = false,
  className = '',
  'aria-label': ariaLabel,
}: Props) {
  const isMobile = useIsMobile()
  const [sheetOpen, setSheetOpen] = useState(false)

  if (isMobile) {
    const selected = value ? options.find((o) => o.id === value) : null
    return (
      <>
        <button
          type="button"
          className={`picker-field__trigger ${className}`}
          onClick={() => setSheetOpen(true)}
          disabled={disabled}
          aria-label={ariaLabel}
          aria-haspopup="dialog"
        >
          <span className={selected ? 'picker-field__value' : 'picker-field__placeholder'}>
            {selected?.label ?? noneLabel}
          </span>
          <ChevronDown size={14} />
        </button>
        <SelectionSheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title={sheetTitle}
          options={options}
          topSection={pinned}
          value={value}
          onChange={onChange}
          allowNone={allowNone}
          noneLabel={noneLabel}
          placeholder={searchPlaceholder}
        />
      </>
    )
  }

  const desktopOptions = [
    ...(allowNone ? [{ id: NONE, label: noneLabel }] : []),
    ...(pinned?.options.map((o) => ({ ...o, group: pinned.label })) ?? []),
    ...options,
  ]
  return (
    <Combobox
      value={value}
      options={desktopOptions}
      onChange={(id) => onChange(id === NONE ? null : id)}
      placeholder={placeholder ?? noneLabel}
      disabled={disabled}
      className={className}
      aria-label={ariaLabel}
    />
  )
}
