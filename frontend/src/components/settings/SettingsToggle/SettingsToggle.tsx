import type { ReactNode } from 'react'

interface Props {
  label: string
  desc?: ReactNode
  checked: boolean
  disabled?: boolean
  onChange: (checked: boolean) => void
}

/**
 * An on/off setting: the whole row is the control, and the control is a
 * switch.
 *
 * Fourteen settings rows used to put a bare checkbox after their text with
 * no <label> — so tapping the words did nothing, a screen reader heard an
 * unnamed checkbox, and on a phone the row wrapped and left a 13px box
 * floating alone under a paragraph, reading as decoration. Two AI rows had
 * their own switches instead, each with its own CSS. This is the one.
 *
 * Styles live with the rest of the settings vocabulary in SettingsShell.css.
 */
export function SettingsToggle({ label, desc, checked, disabled, onChange }: Props) {
  return (
    <label
      className={`settings-row settings-toggle${disabled ? ' settings-toggle--disabled' : ''}`}
    >
      <span className="settings-toggle__text">
        <span className="settings-row__label">{label}</span>
        {desc && <span className="settings-row__desc">{desc}</span>}
      </span>
      <input
        type="checkbox"
        role="switch"
        className="settings-switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  )
}
