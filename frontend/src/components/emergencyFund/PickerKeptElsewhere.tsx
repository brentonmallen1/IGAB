import { useId } from 'react'
import type { ExternalDraft } from './pickerChoice'

/** The picker's Kept elsewhere section: money outside IGAB, said once. */
export function PickerKeptElsewhere({
  draft,
  onChange,
  amountError,
}: {
  draft: ExternalDraft
  onChange: (draft: ExternalDraft) => void
  /** Set when the typed amount does not parse — it blocks Save. */
  amountError: string | null
}) {
  const base = useId()
  return (
    <section className="ef-picker__section" aria-labelledby={`${base}-title`}>
      <h4 id={`${base}-title`} className="ef-picker__title">
        Kept elsewhere
      </h4>
      <label className="dialog-form__field dialog-form__field--inline" htmlFor={`${base}-declared`}>
        <input
          id={`${base}-declared`}
          type="checkbox"
          checked={draft.declared}
          onChange={(e) => onChange({ ...draft, declared: e.target.checked })}
        />
        I keep some of it somewhere IGAB doesn’t track
      </label>
      {draft.declared && (
        <div className="dialog-form__row">
          <label className="dialog-form__field" htmlFor={`${base}-amount`}>
            Amount (optional)
            <input
              id={`${base}-amount`}
              type="text"
              inputMode="decimal"
              value={draft.amount}
              onChange={(e) => onChange({ ...draft, amount: e.target.value })}
              aria-invalid={amountError ? true : undefined}
              aria-describedby={amountError ? `${base}-amount-error` : undefined}
              placeholder="Blank if you’d rather not say"
            />
            {amountError && (
              <span id={`${base}-amount-error`} className="dialog-form__error" role="alert">
                {amountError}
              </span>
            )}
          </label>
          <label className="dialog-form__field" htmlFor={`${base}-note`}>
            Note (optional)
            <input
              id={`${base}-note`}
              type="text"
              value={draft.note}
              onChange={(e) => onChange({ ...draft, note: e.target.value })}
              placeholder="e.g. credit union"
            />
          </label>
        </div>
      )}
    </section>
  )
}
