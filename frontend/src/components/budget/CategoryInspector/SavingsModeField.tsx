import { useUpdateCategory } from '../../../api/categories'
import { apiErrorMessage } from '../../../api/client'
import type { Category, SavingsMode } from '../../../types'
import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import { DEFAULT_MARKER, SAVINGS_MODE_OPTIONS } from '../../../utils/savingsModes'
import './SavingsModeField.css'

const tagName = (key: string) => SYSTEM_TAG_HELP.find((t) => t.key === key)?.name ?? key

interface Props {
  category: Category
  budgetId: string
  /** System keys of the tags on this category, for the conflict line. */
  tagKeys: readonly string[]
}

/**
 * How a savings category's money counts as saved: sent out, or kept here.
 *
 * Renders only for a category the server calls a savings category
 * (`savings_role`). Which option is checked is the served role, never a
 * re-derivation of the tags' default: with no stored choice the role IS the
 * default, so that option carries "(default)"; with a stored choice the marker
 * is dropped and "Use default" clears it. Saved through the category update,
 * which the change log records, so Cmd+Z undoes it.
 */
export function SavingsModeField({ category, budgetId, tagKeys }: Props) {
  const update = useUpdateCategory(budgetId)
  if (category.savings_role === 'none') return null

  const role = category.savings_role
  const explicit = category.savings_mode !== null
  const name = `savings-mode-${category.id}`
  const sinkingFundToo = tagKeys.includes('long_term_expense')

  function choose(mode: SavingsMode | null) {
    if (mode === category.savings_mode) return
    update.mutate({ id: category.id, savings_mode: mode })
  }

  return (
    <fieldset className="savings-mode" disabled={update.isPending}>
      <legend className="savings-mode__legend">Counts as saved when money is:</legend>
      {SAVINGS_MODE_OPTIONS.map((choice) => {
        const id = `${name}-${choice.mode}`
        return (
          <div key={choice.mode} className="savings-mode__option">
            <label className="savings-mode__choice" htmlFor={id}>
              <input
                type="radio"
                id={id}
                name={name}
                value={choice.mode}
                checked={role === choice.mode}
                onChange={() => choose(choice.mode)}
                aria-describedby={`${id}-consequence`}
              />
              <span>
                {choice.label}
                {!explicit && role === choice.mode && (
                  <>
                    {' '}
                    <span className="savings-mode__default">{DEFAULT_MARKER}</span>
                  </>
                )}
              </span>
            </label>
            <p id={`${id}-consequence`} className="savings-mode__consequence">
              {choice.consequence}
            </p>
          </div>
        )
      })}
      {explicit && (
        <button type="button" className="savings-mode__reset" onClick={() => choose(null)}>
          Use default
        </button>
      )}
      {sinkingFundToo && (
        <p className="savings-mode__conflict">
          {/* Named from the served role, not a client list of savings tags:
              Savings and Emergency fund both reach here. */}
          Also tagged {tagName('long_term_expense')}: it counts as savings, not as a sinking fund.
        </p>
      )}
      {update.isError && (
        <p className="inspector-error" role="alert">
          {apiErrorMessage(update.error, 'Could not save how this category counts')}
        </p>
      )}
    </fieldset>
  )
}
