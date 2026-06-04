import { useState, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import './Tooltip.css'

interface Props {
  content: React.ReactNode | null
  children: React.ReactNode
}

export function Tooltip({ content, children }: Props) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<HTMLSpanElement>(null)

  const show = useCallback(() => {
    const rect = ref.current?.getBoundingClientRect()
    if (rect) setPos({ x: rect.left + rect.width / 2, y: rect.top - 8 })
  }, [])

  const hide = useCallback(() => setPos(null), [])

  return (
    <span ref={ref} className="tooltip-host" onMouseEnter={show} onMouseLeave={hide}>
      {children}
      {pos && content != null &&
        createPortal(
          <span
            className="tooltip-popup"
            style={{ left: pos.x, top: pos.y }}
            role="tooltip"
          >
            {content}
          </span>,
          document.body,
        )}
    </span>
  )
}
