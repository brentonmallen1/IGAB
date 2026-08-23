import { Construction } from 'lucide-react'

/**
 * A tab that is planned but not built.
 *
 * Says what is coming and what it will do, rather than pretending the tab does
 * not exist — the roadmap links to these tools, and a reader who follows one
 * deserves an honest answer instead of a dead end.
 */
export function GuidePlaceholder({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="guide-placeholder">
      <Construction size={20} aria-hidden />
      <h2 className="guide-placeholder__title">{title}</h2>
      <div className="guide-placeholder__body">{children}</div>
      <p className="guide-placeholder__note">Not built yet.</p>
    </div>
  )
}
