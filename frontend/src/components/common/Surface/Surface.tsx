import type { HTMLAttributes, ReactNode } from 'react'
import { useStuck } from './useStuck'

export type SurfaceVariant = 'raised' | 'sunken' | 'chrome'

type SurfaceElement =
  'div' | 'section' | 'header' | 'aside' | 'nav' | 'article' | 'footer' | 'dl' | 'ul'

export interface SurfaceProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  as?: SurfaceElement
  /**
   * raised — a card or section on the page canvas (default)
   * sunken — an inset region inside a raised card: scroll wells, table bodies
   * chrome — a toolbar, filter bar, page header or sticky table header
   */
  variant?: SurfaceVariant
  /** Chrome that pins inside its scroll container; gains a shadow once pinned. */
  sticky?: boolean
  /** Dashed outline for a secondary affordance ("Try a sample budget"). */
  dashed?: boolean
  /** Renders a header row; `title` uses the shared section-label typography. */
  title?: ReactNode
  /** Right-aligned controls in the header row. Requires `title` or `header`. */
  actions?: ReactNode
  /** Free-form header content when `title` is not enough. */
  header?: ReactNode
  /** Extra class on the header row. */
  headerClassName?: string
  children?: ReactNode
}

/**
 * The wiring for the `.surface` rules in themes/base.css (variants, the
 * stuck-shadow toggle, header slots). Every page-level card, well and bar goes through
 * here so "what a section looks like" has a single definition.
 */
export function Surface({
  as = 'div',
  variant = 'raised',
  sticky = false,
  dashed = false,
  title,
  actions,
  header,
  headerClassName,
  className,
  children,
  ...rest
}: SurfaceProps) {
  const { ref, stuck } = useStuck<HTMLDivElement>(sticky)
  // Every element in SurfaceElement takes the same HTMLAttributes; typing the
  // tag as 'div' keeps the ref and spread props on one element type.
  const Tag = as as 'div'
  const classes = [
    'surface',
    `surface--${variant}`,
    sticky ? 'surface--sticky' : '',
    sticky && stuck ? 'surface--stuck' : '',
    dashed ? 'surface--dashed' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')
  const hasHeader = title != null || header != null

  return (
    <Tag ref={ref} className={classes} {...rest}>
      {hasHeader && (
        <div className={['surface__header', headerClassName ?? ''].filter(Boolean).join(' ')}>
          {header ?? <span className="section-label surface__title">{title}</span>}
          {actions != null && <div className="surface__actions">{actions}</div>}
        </div>
      )}
      {children}
    </Tag>
  )
}
