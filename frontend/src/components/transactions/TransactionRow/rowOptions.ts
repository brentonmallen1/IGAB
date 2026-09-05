import type { ComboboxOption } from '../../common/Combobox/Combobox'
import type { Category, CategoryGroup, Payee } from '../../../types'

/**
 * What the register row's pickers offer — pure, so the filters are testable
 * without mounting a row.
 *
 * Both lists are filters, not just maps, and both filters are load-bearing:
 * offering the wrong option here does not misdraw a cell, it files money
 * somewhere the user cannot find it.
 */

/** Real payees only. A transfer payee is a destination, not a payee; picking
 *  one would name a transfer the row is not. */
export function payeeOptions(payees: Payee[]): ComboboxOption[] {
  return payees.filter((p) => !p.transfer_account_id).map((p) => ({ id: p.id, label: p.name }))
}

/**
 * `is_categorizable`, like every other category picker — the server decides
 * what a leg may be filed to. Offering the raw list put each card's set-aside
 * envelope in the register's most-used control, under a blank group heading
 * (its group is hidden, so no name resolved), and filing a row there hid the
 * money from the budget entirely.
 */
export function categoryOptions(categories: Category[], groups: CategoryGroup[]): ComboboxOption[] {
  return categories
    .filter((c) => c.is_categorizable)
    .map((c) => ({
      id: c.id,
      label: c.name,
      group: groups.find((g) => g.id === c.category_group_id)?.name ?? '',
    }))
}
