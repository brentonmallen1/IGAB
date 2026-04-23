import { Construction } from 'lucide-react'

interface Props {
  title: string
  description?: string
}

export function ReportPlaceholder({ title, description }: Props) {
  return (
    <div className="report-section">
      <h2 className="report-section__title">{title}</h2>
      <div className="report-loading" style={{ flexDirection: 'column', gap: '8px', minHeight: 300 }}>
        <Construction size={32} style={{ opacity: 0.3 }} />
        <span>{description ?? 'This report is loading data…'}</span>
      </div>
    </div>
  )
}
