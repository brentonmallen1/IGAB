import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import {
  SETTINGS_PAGES,
  filterSections,
  groupedSections,
  neighbours,
  sectionHref,
  sectionIdFromPath,
  type SettingsPageId,
  type SettingsSectionId,
  type VisibleSection,
} from '../../../pages/SettingsPage/settingsSections'
import './SettingsShell.css'

/** What a page hands the shell for one section: its body, and anything that
 *  belongs beside the title (a help icon) or opposite it (an action). */
export interface SectionPanel {
  body: ReactNode
  titleAside?: ReactNode
  actions?: ReactNode
}

/**
 * The settings layout: a nav of grouped section names beside ONE section.
 *
 * It used to be ten sections in one scrolling column with a scroll-spy in
 * the nav, and every section weighed the same — a raised card with a 13px
 * title, which is also the size of a row label. Nothing said where one
 * thing stopped and the next began. Showing a single section gives it a real
 * title, a sentence saying what it is for, and the whole column to itself.
 *
 * The address is the section: `/settings/budget`. Deep links from the
 * palette and from other pages already spelled one; they no longer have to
 * scroll to it. The old `#budget` form is forwarded so nothing bookmarked
 * breaks. A bare `/settings` opens the first section on a desktop; on a
 * phone it is the list, and a section is the screen after it, with a way
 * back — the account page's own list → register pattern.
 *
 * Settings and System both render inside this. The shared settings
 * vocabulary (`settings-row`, `settings-btn`, …) is loaded here too, because
 * every panel that uses it renders inside this shell on one page or the
 * other.
 */
export function SettingsShell({
  page,
  sections,
  panels,
  hints = {},
  navLabel,
  navHeader,
  navFooter,
  children,
}: {
  page: SettingsPageId
  sections: VisibleSection[]
  /** The sections' contents, by id. A visible section with no panel here
   *  is a bug the empty state names rather than hides. */
  panels: Partial<Record<SettingsSectionId, SectionPanel>>
  /** A fact per section, shown beside its name in the nav — which theme,
   *  how many keys, when the last backup was — so a section can be judged
   *  before it is opened. */
  hints?: Partial<Record<SettingsSectionId, ReactNode>>
  navLabel: string
  /** A cross-link above the search box — System's way back to Settings.
   *  It lives in the nav rather than a page-level banner: a title-plus-
   *  subtitle band above the shell repeated what the section's own header
   *  already said, in different type, and doubled the chrome for no reason
   *  Settings didn't also have. */
  navHeader?: ReactNode
  /** A cross-link under the section list (Settings ↔ System). */
  navFooter?: ReactNode
  /** Modals and other things that render regardless of section. */
  children?: ReactNode
}) {
  const isMobile = useIsMobile()
  const location = useLocation()
  const navigate = useNavigate()
  const base = SETTINGS_PAGES[page].path
  const contentRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')

  const activeId = sectionIdFromPath(page, location.pathname)
  const active = sections.find((s) => s.id === activeId) ?? null

  // `/settings#budget` was the address until sections got their own; the
  // palette, the budget picker and anything a person bookmarked spelled it.
  // Forward rather than 404: a link that worked last week still works.
  useEffect(() => {
    if (!activeId && location.hash.length > 1) {
      navigate(`${base}/${location.hash.slice(1)}`, { replace: true })
    }
  }, [activeId, location.hash, base, navigate])

  // A desktop has room for a section beside the list, so a bare path shows
  // the first one rather than an empty column. A phone shows the list — that
  // is the screen the person asked for. Only a BARE path is forwarded: a
  // section that is not (yet) visible stays put, because admin sections
  // arrive after /auth/me resolves and forwarding would bounce a deep link
  // to `/system/users` away before it had a chance to render.
  useEffect(() => {
    if (!isMobile && !activeId && !location.hash && sections.length > 0) {
      navigate(sectionHref(sections[0]), { replace: true })
    }
  }, [isMobile, activeId, location.hash, sections, navigate])

  // A new section starts at its top; the column keeps its own scroll.
  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0
  }, [activeId])

  const matches = filterSections(sections, query)
  const groups = groupedSections(matches)
  const { prev, next } = active ? neighbours(sections, active.id) : { prev: null, next: null }
  const panel = active ? panels[active.id] : undefined

  // On a phone the two columns are two screens. Which one this is follows
  // the address, so back (chevron, edge-swipe, browser) lands on the list.
  const mode = !isMobile ? 'split' : active ? 'detail' : 'list'

  return (
    <div className={`settings-page settings-page--${mode}`}>
      <nav className="settings-nav" aria-label={navLabel}>
        {navHeader && <div className="settings-nav__pre">{navHeader}</div>}
        <label className="settings-nav__search">
          <Search size={13} aria-hidden="true" />
          <input
            id={`${page}-section-search`}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              // Enter opens the first match: type "back", press Enter.
              if (e.key === 'Enter' && matches[0]) navigate(sectionHref(matches[0]))
            }}
            placeholder="Search settings"
            aria-label={`Search ${navLabel.toLowerCase()}`}
          />
        </label>

        {groups.length === 0 && <div className="settings-nav__none">Nothing matches.</div>}

        {groups.map((group) => (
          <div key={group.id} className="settings-nav__group">
            <div className="settings-nav__group-label">{group.label}</div>
            {group.sections.map(({ id, label, warn }) => (
              <NavLink
                key={id}
                to={sectionHref({ id, page })}
                className={({ isActive }) =>
                  `settings-nav__link ${isActive ? 'settings-nav__link--active' : ''}`
                }
                title={warn}
              >
                <span className="settings-nav__name">
                  {label}
                  {warn && (
                    <>
                      <span className="settings-nav__warn" aria-hidden />
                      <span className="sr-only">{` — ${warn}`}</span>
                    </>
                  )}
                </span>
                {hints[id] != null && <span className="settings-nav__hint">{hints[id]}</span>}
                <ChevronRight size={14} className="settings-nav__chevron" aria-hidden="true" />
              </NavLink>
            ))}
          </div>
        ))}

        {navFooter && <div className="settings-nav__footer">{navFooter}</div>}
      </nav>

      <div className="settings-content" ref={contentRef}>
        {active ? (
          <section
            className="settings-section"
            id={active.id}
            aria-labelledby={`${active.id}-title`}
          >
            <Link to={base} className="settings-section__back">
              <ChevronLeft size={16} aria-hidden="true" />
              {SETTINGS_PAGES[page].label}
            </Link>
            <header className="settings-section__head">
              <div className="settings-section__heading">
                <h1 id={`${active.id}-title`} className="settings-section__title">
                  {active.label}
                  {panel?.titleAside}
                </h1>
                <p className="settings-section__desc">{active.description}</p>
              </div>
              {panel?.actions && <div className="settings-section__actions">{panel.actions}</div>}
            </header>

            {panel ? (
              <div className="settings-section__body">{panel.body}</div>
            ) : (
              <div className="settings-section__empty">
                This section has nothing to show right now.
              </div>
            )}

            {(prev || next) && (
              <nav className="settings-section__pager" aria-label="Neighbouring sections">
                {prev ? (
                  <Link to={sectionHref(prev)} className="settings-section__pager-link">
                    <ChevronLeft size={14} aria-hidden="true" />
                    <span>{prev.label}</span>
                  </Link>
                ) : (
                  <span />
                )}
                {next && (
                  <Link
                    to={sectionHref(next)}
                    className="settings-section__pager-link settings-section__pager-link--next"
                  >
                    <span>{next.label}</span>
                    <ChevronRight size={14} aria-hidden="true" />
                  </Link>
                )}
              </nav>
            )}
          </section>
        ) : activeId ? (
          // Named but not visible: an admin section before /auth/me answers,
          // a budget section with no budget open, or a typo.
          <div className="settings-section__empty">
            There is no “{activeId}” here.{' '}
            <Link to={base}>Back to {SETTINGS_PAGES[page].label}</Link>
          </div>
        ) : null}
      </div>

      {children}
    </div>
  )
}
