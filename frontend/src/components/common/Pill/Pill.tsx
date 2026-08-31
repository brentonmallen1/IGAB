import type { HTMLAttributes, ReactNode } from 'react'
import './Pill.css'

export type PillTone = 'default' | 'outline' | 'positive'

export interface PillProps extends HTMLAttributes<HTMLSpanElement> {
  /** outline — no fill, muted text; positive — connected / healthy state */
  tone?: PillTone
  /** Small-caps label (account and liability type badges). */
  caps?: boolean
  children: ReactNode
}

/**
 * A status chip: an inline label with a tint fill and hairline edge so it
 * reads as a discrete token on every surface. One implementation for the
 * account header status row and the liability type badges.
 */
export function Pill({ tone = 'default', caps = false, className, children, ...rest }: PillProps) {
  const classes = [
    'pill',
    tone !== 'default' ? `pill--${tone}` : '',
    caps ? 'pill--caps' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <span className={classes} {...rest}>
      {children}
    </span>
  )
}
