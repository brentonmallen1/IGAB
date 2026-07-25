import { X } from 'lucide-react'
import { SHORTCUTS, formatCombo, type ShortcutDef } from '../../../keyboard/shortcuts'
import './ShortcutHelp.css'

interface Props {
  onClose: () => void
}

const GROUPS: ShortcutDef['group'][] = ['Global', 'Transactions']

export function ShortcutHelp({ onClose }: Props) {
  const defs = Object.values(SHORTCUTS) as ShortcutDef[]

  return (
    <div
      className="shortcut-help-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="shortcut-help" role="dialog" aria-modal aria-labelledby="shortcut-help-title">
        <div className="shortcut-help__header">
          <span id="shortcut-help-title" className="shortcut-help__title">Keyboard shortcuts</span>
          <button className="shortcut-help__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="shortcut-help__body">
          {GROUPS.map((group) => (
            <div key={group} className="shortcut-help__group">
              <div className="shortcut-help__group-title">{group}</div>
              <ul>
                {defs
                  .filter((d) => d.group === group)
                  .map((d) => (
                    <li key={d.combo + d.label} className="shortcut-help__row">
                      <span className="shortcut-help__label">{d.label}</span>
                      <kbd className="kbd">{formatCombo(d.combo)}</kbd>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
