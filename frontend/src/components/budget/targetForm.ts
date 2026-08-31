/**
 * The target form's vocabulary and its one validation rule.
 *
 * Two components render this form — the standalone editor and the inspector
 * section — and both carried their own copy of the type list and the payload
 * construction, including the same bug: `parseFloat(amount) || 0`.
 *
 * That is wrong twice. `parseFloat` mis-reads the separator conventions
 * `utils/money` explicitly supports (`parseFloat("1.234,56")` is `1.234`), and
 * `|| 0` turns anything it cannot read into a zero target — which can never be
 * underfunded, so the row silently stops asking for money. Both files sit next
 * to comments elsewhere in the budget code stating the rule this broke:
 * unparseable input must never quietly write $0.
 */
import { parseAmountInput } from '../../utils/money'

export const TARGET_TYPES = [
  { value: 'monthly_funding', label: 'Monthly Funding' },
  { value: 'weekly_funding', label: 'Weekly Funding' },
  { value: 'savings_balance', label: 'Savings Balance' },
  { value: 'needed_for_spending', label: 'Needed for Spending' },
] as const

export interface TargetPayload {
  target_type: string
  target_amount: number
  target_date: string | null
}

export type TargetFormResult = { ok: true; payload: TargetPayload } | { ok: false; error: string }

/** Build the upsert payload, or say why it cannot be built. */
export function buildTargetPayload(
  targetType: string,
  amount: string,
  targetDate: string
): TargetFormResult {
  const parsed = parseAmountInput(amount)
  if (isNaN(parsed)) return { ok: false, error: 'Enter an amount.' }
  if (parsed <= 0) return { ok: false, error: 'A target has to be more than zero.' }
  return {
    ok: true,
    payload: {
      target_type: targetType,
      target_amount: parsed,
      target_date: targetDate || null,
    },
  }
}
