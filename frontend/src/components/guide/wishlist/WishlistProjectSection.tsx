import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { WishlistProject } from '../../../api/wishlist'
import { useFormatters } from '../../../hooks/useFormatters'
import { projectLine } from './wishlistCopy'

interface Props {
  project: WishlistProject | null
  count: number
  onEdit?: () => void
  onDelete?: () => void
  children: ReactNode
}

/** A project's wishes under its rollup — "2 of 3 affordable now · $2,400 · all by Apr 2027". */
export function WishlistProjectSection({ project, count, onEdit, onDelete, children }: Props) {
  const [open, setOpen] = useState(true)
  const fmt = useFormatters()
  const title = project?.name ?? 'Other wants'
  return (
    <section className="wish-project">
      <header className="wish-project__head">
        <button
          type="button"
          className="wish-project__toggle"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
          <h3 className="wish-project__name">{title}</h3>
          <span className="wish-project__count">{count}</span>
        </button>
        {project && (
          <div className="wish-project__meta">
            <span className="wish-project__line">{projectLine(project, fmt)}</span>
            <span className="wish-project__envelope">
              {project.category_name ? `funded from ${project.category_name}` : 'no funding category yet'}
            </span>
            {onEdit && (
              <button type="button" className="guide-link-button" onClick={onEdit}>
                Edit
              </button>
            )}
            {onDelete && (
              <button type="button" className="guide-link-button" onClick={onDelete}>
                Delete
              </button>
            )}
          </div>
        )}
      </header>
      {open && <div className="wish-project__body">{children}</div>}
    </section>
  )
}
