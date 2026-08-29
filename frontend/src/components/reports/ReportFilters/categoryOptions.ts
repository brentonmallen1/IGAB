import type { BudgetView, Category } from '../../../types'
import { renderableCategories } from '../../budget/budgetGroups'
import { groupByView } from '../../budget/BudgetTable/viewGrouping'
import type { MultiSelectOption } from './MultiSelectCombobox'

/**
 * Options for the report category picker, bucketed the way the chart is.
 *
 * With a view active the picker must agree with what the chart draws: same
 * groups, and nothing offered that the view leaves out. A category selectable
 * here but absent from the chart reads as a broken filter.
 *
 * The view rules themselves live in `groupByView` and are not restated here —
 * they were, once, and the two copies were one edit away from disagreeing.
 */
export function categoryOptions(
  categories: Category[],
  groupName: Map<string, string>,
  view: BudgetView | null
): MultiSelectOption[] {
  // Hidden categories are left out; card set-aside envelopes too, and for a
  // stronger reason — nothing can ever be filed to one, so offering it here
  // is a filter that can only ever return an empty chart. `is_hidden` is
  // kept rather than swapped for `is_categorizable`: a category in a hidden
  // *group* still holds real spending worth charting.
  const visible = renderableCategories(categories).filter((c) => !c.is_hidden)
  if (!view) {
    return visible.map((c) => ({
      id: c.id,
      label: c.name,
      group: groupName.get(c.category_group_id) ?? '',
    }))
  }

  // groupByView wants a budget id only to stamp the synthetic group rows it
  // returns; those are read for their names here and otherwise discarded.
  const { groups, byGroup } = groupByView(view, visible, visible[0]?.budget_id ?? '')
  return groups.flatMap((g) =>
    (byGroup.get(g.id) ?? []).map((c) => ({ id: c.id, label: c.name, group: g.name }))
  )
}
