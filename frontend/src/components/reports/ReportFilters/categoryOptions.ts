import type { BudgetView, Category } from '../../../types'
import type { MultiSelectOption } from './MultiSelectCombobox'

/**
 * Options for the report category picker, bucketed the way the chart is.
 *
 * With a view active the picker must agree with what the chart draws: same
 * groups, and nothing offered that the view leaves out. A category selectable
 * here but absent from the chart reads as a broken filter.
 */
export function categoryOptions(
  categories: Category[],
  groupName: Map<string, string>,
  view: BudgetView | null
): MultiSelectOption[] {
  const visible = categories.filter((c) => !c.is_hidden)
  if (!view) {
    return visible.map((c) => ({
      id: c.id,
      label: c.name,
      group: groupName.get(c.category_group_id) ?? '',
    }))
  }

  const placement = new Map(view.placements.map((p) => [p.category_id, p]))
  const viewGroupName = new Map(view.groups.map((g) => [g.id, g.name]))

  return visible
    .filter((c) => {
      const p = placement.get(c.id)
      if (p?.is_hidden) return false
      // Unplaced categories are only offered when the view still shows them.
      return !((p?.group_id ?? null) === null && view.hide_unassigned)
    })
    .map((c) => {
      const gid = placement.get(c.id)?.group_id ?? null
      return {
        id: c.id,
        label: c.name,
        group: gid ? (viewGroupName.get(gid) ?? 'Unassigned') : 'Unassigned',
      }
    })
}
