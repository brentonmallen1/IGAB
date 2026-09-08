import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ArrowLeft, ChevronLeft } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { parentRoute } from '../../../utils/routes'
import './PageHeader.css'

/** Where the app header puts a page's title on a phone; rendered by Header. */
export const PAGE_HEADER_SLOT_ID = 'header-page-slot'

export interface PageHeaderProps {
  /** The page's name. A string, so the phone chrome can show it. */
  title: string
  /** Rendered in place of the plain title on a desktop (an icon beside it). */
  titleNode?: ReactNode
  /** A back link. `true` derives the destination from the route (a register
   *  returns to Accounts); an object names it. */
  back?: true | { to: string; label: string }
  /** Inline beside the title: a count, pills. */
  meta?: ReactNode
  /** A line under the title. */
  subtitle?: ReactNode
  /** Buttons for the page. */
  actions?: ReactNode
  className?: string
}

/**
 * The one page header.
 *
 * Twelve pages each hand-rolled `<div className="x__header"><h1 …>` with its
 * own spacing and, on a phone, its own way of not fitting — Accounts cut its
 * third button off at the screen edge, and every page spent a band of a
 * short screen on a title the bottom nav had already stated.
 *
 * On a desktop it is the familiar band: back link, title with its meta,
 * subtitle, actions on the right. On a phone the title and the back chevron
 * move into the app header's slot (see Header), so the page's own band holds
 * only what a phone still needs — the subtitle, meta and actions — and a
 * page with none of those spends no band at all.
 */
export function PageHeader({
  title,
  titleNode,
  back,
  meta,
  subtitle,
  actions,
  className,
}: PageHeaderProps) {
  const isMobile = useIsMobile()
  const { pathname } = useLocation()
  const [slot, setSlot] = useState<HTMLElement | null>(null)

  // The slot is a sibling rendered by Header in the same commit; it exists by
  // the time effects run. Pages outside the shell (the budget picker, System)
  // have no slot and keep their band. Looked up on the next frame so the
  // first paint is the in-page band, never a flash of an empty header.
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      setSlot(isMobile ? document.getElementById(PAGE_HEADER_SLOT_ID) : null)
    })
    return () => cancelAnimationFrame(frame)
  }, [isMobile, pathname])

  const backLink = back === true ? { to: parentRoute(pathname), label: 'Back' } : back ? back : null

  const inChrome = isMobile && slot !== null

  const chrome =
    inChrome &&
    createPortal(
      <div className="page-header__chrome">
        {backLink && (
          <Link
            to={backLink.to}
            className="page-header__chrome-back"
            aria-label={backLink.label === 'Back' ? 'Back' : `Back to ${backLink.label}`}
          >
            <ChevronLeft size={22} />
          </Link>
        )}
        <h1 className="page-header__chrome-title">{title}</h1>
      </div>,
      slot
    )

  const hasBand = !inChrome || meta || subtitle || actions
  if (!hasBand) return <>{chrome}</>

  return (
    <>
      {chrome}
      <div
        className={['page-header', inChrome ? 'page-header--band-only' : '', className]
          .filter(Boolean)
          .join(' ')}
      >
        {!inChrome && backLink && (
          <Link to={backLink.to} className="page-header__back">
            <ArrowLeft size={15} />
            <span>{backLink.label}</span>
          </Link>
        )}
        <div className="page-header__text">
          <div className="page-header__title-row">
            {!inChrome && <h1 className="page-header__title">{titleNode ?? title}</h1>}
            {meta && <div className="page-header__meta">{meta}</div>}
          </div>
          {subtitle && <div className="page-header__subtitle">{subtitle}</div>}
        </div>
        {actions && <div className="page-header__actions">{actions}</div>}
      </div>
    </>
  )
}
