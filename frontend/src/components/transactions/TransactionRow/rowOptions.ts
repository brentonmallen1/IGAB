import type { ComboboxOption } from '../../common/Combobox/Combobox'
import type { Payee } from '../../../types'
import { choosablePayees } from '../../../utils/payees'

/**
 * What the register row's payee picker offers — pure, so the filter is
 * testable without mounting a row.
 *
 * Its category picker offers `filingCategoryOptions` (utils/categoryPickers),
 * the list every picker that files a leg shares. It lived here until the
 * split editor, bulk categorize and quick-add turned out to spell it three
 * more ways.
 */

/** Real payees only. A transfer payee is a destination, not a payee; picking
 *  one would name a transfer the row is not. */
export function payeeOptions(payees: Payee[]): ComboboxOption[] {
  return choosablePayees(payees).map((p) => ({ id: p.id, label: p.name }))
}
