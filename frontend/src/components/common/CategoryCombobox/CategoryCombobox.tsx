import type { ComboboxOption } from '../Combobox/Combobox'
import { PickerField } from '../PickerField/PickerField'

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
 * GroupedCategoryOptions — a `PickerField` (Combobox on desktop,
 * SelectionSheet on a phone) over the categories, grouped by their group.
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
  const options: ComboboxOption[] = [
    ...(topOptions ?? []),
    ...groups.flatMap((g) => g.cats.map((c) => ({ id: c.id, label: c.name, group: g.group.name }))),
  ]
  return (
    <PickerField
      value={value}
      onChange={onChange}
      options={options}
      allowNone={allowNone}
      noneLabel={noneLabel}
      placeholder={placeholder}
      sheetTitle={sheetTitle}
      searchPlaceholder="Search categories…"
      disabled={disabled}
      className={className}
      aria-label={ariaLabel}
    />
  )
}
