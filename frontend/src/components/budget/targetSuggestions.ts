/**
 * Which suggestion chips the target form offers, and what each one fills.
 *
 * Pure presentation of served figures (`TargetSuggestions`): the server
 * decides the numbers, this decides which field each one makes sense in for
 * the shape being edited. Nothing here is arithmetic — a weekly target gets
 * no spending chip rather than an invented monthly-to-weekly conversion.
 */
import type { TargetSuggestions } from '../../types'
import { targetTakesLimit } from './targetForm'

/** The form field a chip writes into. */
export type SuggestionField = 'amount' | 'limit'

export interface SuggestionChip {
  key: 'average' | 'peak_spent' | 'peak_available'
  label: string
  /** Longer wording for the chip's title and accessible name. */
  title: string
  value: number
  field: SuggestionField
}

export function suggestionChips(
  suggestions: TargetSuggestions | undefined,
  targetType: string,
  formatMoney: (amount: number) => string,
  formatMonth: (month: string) => string
): SuggestionChip[] {
  if (!suggestions || suggestions.months_counted === 0) return []
  const months = suggestions.months_counted
  const span = months === 1 ? 'the last month' : `the last ${months} months`
  const chips: SuggestionChip[] = []
  const monthly = targetType === 'monthly_funding'
  const savings = targetType === 'savings_balance'

  if (monthly && suggestions.average_spent > 0) {
    chips.push({
      key: 'average',
      label: `Avg ${formatMoney(suggestions.average_spent)}/mo`,
      title: `Average spent per month over ${span}`,
      value: suggestions.average_spent,
      field: 'amount',
    })
  }
  if ((monthly || savings) && suggestions.peak_spent != null && suggestions.peak_spent_month) {
    chips.push({
      key: 'peak_spent',
      label: `Peak month ${formatMoney(suggestions.peak_spent)}`,
      title: `Most spent in one month over ${span} (${formatMonth(suggestions.peak_spent_month)})`,
      value: suggestions.peak_spent,
      field: 'amount',
    })
  }
  if (suggestions.peak_available != null && suggestions.peak_available_month) {
    // The highest balance is a ceiling: the stop of a funding target, or the
    // balance a savings target keeps.
    const field: SuggestionField | null = targetTakesLimit(targetType)
      ? 'limit'
      : savings
        ? 'amount'
        : null
    if (field) {
      chips.push({
        key: 'peak_available',
        label: `Peak balance ${formatMoney(suggestions.peak_available)}`,
        title: `Most this envelope held at a month's end over ${span} (${formatMonth(suggestions.peak_available_month)})`,
        value: suggestions.peak_available,
        field,
      })
    }
  }
  return chips
}

/** What a chip writes into its field: the amount as the input shows it. */
export function chipInputValue(chip: SuggestionChip): string {
  return chip.value.toFixed(2)
}
