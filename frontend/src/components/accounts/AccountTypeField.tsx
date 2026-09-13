import { useId } from 'react'
import { HelpCircle } from 'lucide-react'
import './AccountSettingsModal.css'

interface Props {
  value: string
  options: readonly { key: string; label: string }[]
  onChange: (key: string) => void
  onHelp: () => void
}

/** The account-type select with its "what do these mean?" button, for the New
 *  Account and Account Settings forms. The label is a `<label htmlFor>` rather
 *  than a wrapper so the help button is not part of the select's name. What a
 *  type change resets is the caller's: a new account takes the type's
 *  on-budget default, an existing one keeps its own. */
export function AccountTypeField({ value, options, onChange, onHelp }: Props) {
  const id = useId()
  return (
    <div className="dialog-form__field">
      <span>
        <label htmlFor={id}>Type</label>
        <button
          type="button"
          className="acct-modal__type-help"
          onClick={onHelp}
          aria-label="What do account types mean?"
          title="What do account types mean?"
        >
          <HelpCircle size={12} />
        </button>
      </span>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((t) => (
          <option key={t.key} value={t.key}>
            {t.label}
          </option>
        ))}
      </select>
    </div>
  )
}
