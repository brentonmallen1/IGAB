import { useRef, useEffect } from 'react'
import type { LucideIcon } from 'lucide-react'
import './ContextMenu.css'

export interface ContextMenuItem {
  id: string
  label: string
  icon?: LucideIcon
  disabled?: boolean
  danger?: boolean
  separator?: boolean
  shortcut?: string
}

interface Props {
  items: ContextMenuItem[]
  onSelect: (id: string) => void
  onClose: () => void
  position?: { x: number; y: number }
  className?: string
}

export function ContextMenu({ items, onSelect, onClose, position, className = '' }: Props) {
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose])

  const style = position
    ? { position: 'fixed' as const, top: position.y, left: position.x }
    : undefined

  return (
    <div ref={menuRef} className={`context-menu ${className}`} style={style} role="menu">
      {items.map((item) => {
        if (item.separator) {
          return <div key={item.id} className="context-menu__separator" />
        }
        const Icon = item.icon
        return (
          <button
            key={item.id}
            className={`context-menu__item ${item.danger ? 'context-menu__item--danger' : ''} ${item.disabled ? 'context-menu__item--disabled' : ''}`}
            onClick={() => { if (!item.disabled) { onSelect(item.id); onClose() } }}
            disabled={item.disabled}
            role="menuitem"
          >
            {Icon && (
              <span className="context-menu__icon">
                <Icon size={14} />
              </span>
            )}
            <span className="context-menu__label">{item.label}</span>
            {item.shortcut && (
              <span className="context-menu__shortcut">{item.shortcut}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
