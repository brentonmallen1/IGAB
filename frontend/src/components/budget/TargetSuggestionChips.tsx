import { useTargetSuggestions } from '../../api/targets'
import { useFormatters } from '../../hooks/useFormatters'
import { useAppStore } from '../../stores/appStore'
import { chipInputValue, suggestionChips, type SuggestionField } from './targetSuggestions'
import './TargetSuggestionChips.css'

interface Props {
  categoryId: string
  targetType: string
  /** Write a suggested amount into the form's amount or Stop-at field. */
  onPick: (field: SuggestionField, value: string) => void
}

/** The target form's "Suggest" row: one-tap amounts from the category's last
 *  twelve months. Draws nothing until there is something to suggest. Both
 *  target forms render it, so the chips and their wording live once. */
export function TargetSuggestionChips({ categoryId, targetType, onPick }: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { formatMoney, formatMonth } = useFormatters()
  const { data } = useTargetSuggestions(budgetId, categoryId)
  const chips = suggestionChips(data, targetType, formatMoney, formatMonth)
  if (chips.length === 0) return null

  return (
    <div className="target-suggest" role="group" aria-label="Suggested amounts">
      <span className="target-suggest__label">Suggest</span>
      <ul className="target-suggest__chips">
        {chips.map((chip) => (
          <li key={chip.key}>
            <button
              type="button"
              className="target-suggest__chip"
              title={chip.title}
              aria-label={`${chip.label}: ${chip.title}`}
              onClick={() => onPick(chip.field, chipInputValue(chip))}
            >
              {chip.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
