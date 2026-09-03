import { SHORTCUTS, formatCombo, type ShortcutDef } from '../../../keyboard/shortcuts'
import { Dialog } from '../Dialog/Dialog'
import './ShortcutHelp.css'

interface Props {
  onClose: () => void
}

const GROUPS: ShortcutDef['group'][] = ['Global', 'Transactions']

export function ShortcutHelp({ onClose }: Props) {
  const defs = Object.values(SHORTCUTS) as ShortcutDef[]

  return (
    <Dialog
      title="Keyboard shortcuts"
      onClose={onClose}
      historyKey="shortcut-help"
      className="shortcut-help"
    >
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
    </Dialog>
  )
}
