import { useState } from 'react'

import { useSettings, useUpdateSetting } from '../../api/settings'

/**
 * One whole-number app setting, saved on blur.
 *
 * Extracted from BackupsPanel when the snapshot schedule needed the same row:
 * a second copy would have been two places to keep the commit-on-blur rule,
 * the bounds message and the failure text in step.
 *
 * The bounds are stated here AND enforced by the server (api/v1/settings.py
 * holds the same pair). That duplication is deliberate and bounded — it is
 * the split-editor case: the field has to answer while the person is typing,
 * before any round trip. The server's copy is the one that decides.
 */
interface NumberSettingRowProps {
  label: string
  desc: string
  settingKey: string
  min: number
  max: number
}

export function NumberSettingRow({ label, desc, settingKey, min, max }: NumberSettingRowProps) {
  const { data: appSettings } = useSettings()
  const updateSetting = useUpdateSetting()
  const saved = appSettings?.find((s) => s.key === settingKey)?.value ?? ''
  const [draft, setDraft] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function commit() {
    if (draft === null || draft === saved) {
      setDraft(null)
      return
    }
    const n = Number(draft)
    if (!Number.isInteger(n) || n < min || n > max) {
      setError(`Must be between ${min} and ${max}`)
      return
    }
    setError(null)
    try {
      await updateSetting.mutateAsync({ key: settingKey, value: String(n) })
      setDraft(null)
    } catch {
      setError('Could not save — is the server reachable?')
    }
  }

  return (
    <div className="settings-row">
      <div>
        <div className="settings-row__label">{label}</div>
        <div className="settings-row__desc">{desc}</div>
        {error && <div className="bkp-field-error">{error}</div>}
      </div>
      <input
        type="number"
        inputMode="numeric"
        className="settings-input bkp-number-input"
        min={min}
        max={max}
        value={draft ?? saved}
        onChange={(e) => {
          setDraft(e.target.value)
          setError(null)
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        }}
      />
    </div>
  )
}
