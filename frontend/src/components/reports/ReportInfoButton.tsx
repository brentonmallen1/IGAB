import { useState, useRef, useEffect } from 'react'
import { Info, X } from 'lucide-react'
import './ReportInfoButton.css'

interface Props {
  title: string
  children: React.ReactNode
}

export function ReportInfoButton({ title, children }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="report-info" ref={ref}>
      <button
        className="report-info__btn"
        onClick={() => setOpen((v) => !v)}
        type="button"
        aria-label="Report information"
      >
        <Info size={15} />
      </button>
      {open && (
        <div className="report-info__panel">
          <div className="report-info__header">
            <span className="report-info__title">{title}</span>
            <button className="report-info__close" onClick={() => setOpen(false)} type="button">
              <X size={13} />
            </button>
          </div>
          <div className="report-info__body">{children}</div>
        </div>
      )}
    </div>
  )
}
