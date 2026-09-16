import { useId } from 'react'
import type { FundAccountCandidate } from '../../api/emergencyFund'
import { useFormatters } from '../../hooks/useFormatters'
import { turnsOnSavings } from './pickerChoice'

/** The picker's Accounts section: every off-budget account the fund may count. */
export function PickerAccounts({
  candidates,
  checked,
  onToggle,
}: {
  candidates: readonly FundAccountCandidate[]
  checked: ReadonlySet<string>
  onToggle: (id: string) => void
}) {
  const { formatMoney } = useFormatters()
  const base = useId()
  const alsoSavings = turnsOnSavings(candidates, checked)

  return (
    <section className="ef-picker__section" aria-labelledby={`${base}-title`}>
      <h4 id={`${base}-title`} className="ef-picker__title">
        Accounts
      </h4>
      <p className="dialog-form__hint">
        Off-budget accounts only. An on-budget account’s money is already in its envelopes — tag the
        envelopes that hold it instead.
      </p>
      {candidates.length === 0 ? (
        <p className="ef-picker__empty">No off-budget accounts to choose from.</p>
      ) : (
        <ul className="ef-picker__accounts">
          {candidates.map((c) => {
            const id = `${base}-${c.id}`
            return (
              <li key={c.id} className="ef-picker__account">
                <label className="dialog-form__field dialog-form__field--inline" htmlFor={id}>
                  <input
                    id={id}
                    type="checkbox"
                    checked={checked.has(c.id)}
                    onChange={() => onToggle(c.id)}
                    aria-describedby={alsoSavings.has(c.id) ? `${id}-also` : undefined}
                  />
                  <span className="ef-picker__account-name">{c.name}</span>
                  <span className="ef-picker__account-balance tabular">
                    {formatMoney(c.balance)}
                  </span>
                </label>
                {alsoSavings.has(c.id) && (
                  <p id={`${id}-also`} className="dialog-form__hint ef-picker__also">
                    Also turns on Counts as savings
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
