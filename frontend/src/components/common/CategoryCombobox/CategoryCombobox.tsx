import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Combobox, type ComboboxOption } from '../Combobox/Combobox'
import { SelectionSheet } from '../SelectionSheet/SelectionSheet'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import './CategoryCombobox.css'

const NONE = '__none__'

export interface CategoryComboboxGroup {
  group: { id: string; name: string }
  cats: { id: string; name: string }[]
}

interface Props {
  value: string | null
  onChange: (id: string | null) => void
  groups: CategoryComboboxGroup[]
  /** Ungrouped options pinned before the categories (e.g. "Ready to Assign") */
  topOptions?: ComboboxOption[]
  /** Offer an explicit "none" choice that selects null */
  allowNone?: boolean
  noneLabel?: string
  placeholder?: string
  sheetTitle?: string
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

/**
 * Searchable, theme-aware category picker replacing native <select> +
 * GroupedCategoryOptions: a Combobox dropdown on desktop, a full-height
 * SelectionSheet on mobile (native pickers there are unsearchable and
 * unthemed).
 */
export function CategoryCombobox({
  value,
  onChange,
  groups,
  topOptions,
  allowNone = false,
  noneLabel = 'No category',
  placeholder,
  sheetTitle = 'Category',
  disabled = false,
  className = '',
  'aria-label': ariaLabel,
}: Props) {
  const isMobile = useIsMobile()
  const [sheetOpen, setSheetOpen] = useState(false)

  const options: ComboboxOption[] = [
    ...(topOptions ?? []),
    ...groups.flatMap((g) =>
      g.cats.map((c) => ({ id: c.id, label: c.name, group: g.group.name }))
    ),
  ]

  if (isMobile) {
    const selected = value ? options.find((o) => o.id === value) : null
    return (
      <>
        <button
          type="button"
          className={`category-combobox__trigger ${className}`}
          onClick={() => setSheetOpen(true)}
          disabled={disabled}
          aria-label={ariaLabel}
          aria-haspopup="dialog"
        >
          <span
            className={
              selected ? 'category-combobox__value' : 'category-combobox__placeholder'
            }
          >
            {selected?.label ?? noneLabel}
          </span>
          <ChevronDown size={14} />
        </button>
        <SelectionSheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title={sheetTitle}
          options={options}
          value={value}
          onChange={onChange}
          allowNone={allowNone}
          noneLabel={noneLabel}
          placeholder="Search categories…"
        />
      </>
    )
  }

  const desktopOptions = allowNone ? [{ id: NONE, label: noneLabel }, ...options] : options
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
