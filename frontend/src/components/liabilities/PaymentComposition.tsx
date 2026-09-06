import { Plus, X } from 'lucide-react'
import type { PaymentComponentInput, PaymentComponentKind } from '../../api/liabilities'
import {
  COMPONENT_KINDS,
  MAX_COMPONENTS,
  blankComponent,
  declaredTotal,
  invalidComponentIndexes,
} from './compositionRows'
import './PaymentComposition.css'

/**
 * The rest of the monthly bill: escrowed tax, insurance, PMI, HOA dues.
 *
 * Optional, and additive to the principal-and-interest payment beside it. It
 * exists because "minimum payment" is not the number on a mortgage statement
 * and the app never said so. Enter the whole bill and every payoff figure
 * runs years early; enter P&I correctly and the other several hundred a month
 * has nowhere to go, so the app cannot show you the bill you actually pay or
 * notice PMI outliving the equity that justified it.
 *
 * Nothing here reaches a projection. That is the point of separating them:
 * the schedule runs on P&I exactly as before, and these sit next to it.
 */

interface Props {
  rows: PaymentComponentInput[]
  onChange: (rows: PaymentComponentInput[]) => void
  /** The P&I field's current value, so the total can be shown live. */
  principalAndInterest: string
  formatMoney: (n: number) => string
}

export function PaymentComposition({ rows, onChange, principalAndInterest, formatMoney }: Props) {
  const invalid = new Set(invalidComponentIndexes(rows))
  const total = declaredTotal(principalAndInterest, rows)

  function update(index: number, patch: Partial<PaymentComponentInput>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  return (
    <div className="payment-composition">
      <div className="payment-composition__intro">
        Leave this empty unless your servicer bills more than the loan. Whatever you add here is
        counted as part of the bill and never as paying down the debt.
      </div>

      {rows.length > 0 && (
        <ul className="payment-composition__rows">
          {rows.map((row, index) => (
            <li key={index} className="payment-composition__row">
              <select
                aria-label="What this is"
                value={row.kind}
                onChange={(e) => update(index, { kind: e.target.value as PaymentComponentKind })}
              >
                {COMPONENT_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                aria-label="Name"
                placeholder={COMPONENT_KINDS.find((k) => k.value === row.kind)?.label}
                value={row.label ?? ''}
                onChange={(e) => update(index, { label: e.target.value })}
              />
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                aria-label="Amount per month"
                placeholder="0.00"
                className={invalid.has(index) ? 'is-invalid' : undefined}
                value={row.amount}
                onChange={(e) => update(index, { amount: e.target.value })}
              />
              <button
                type="button"
                aria-label="Remove this part of the payment"
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
              >
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="payment-composition__foot">
        <button
          type="button"
          className="payment-composition__add"
          onClick={() => onChange([...rows, blankComponent()])}
          disabled={rows.length >= MAX_COMPONENTS}
        >
          <Plus size={12} aria-hidden /> Add part of the payment
        </button>
        {total !== null && rows.length > 0 && (
          // The number to hold against a statement — the only way to check
          // that the split entered here is the right one.
          <span className="payment-composition__total">
            Your full bill: <strong>{formatMoney(total)}</strong> a month
          </span>
        )}
      </div>
    </div>
  )
}
