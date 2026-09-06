import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import type { VisibleSection } from '../../../pages/SettingsPage/settingsSections'
import './SettingsShell.css'

/**
 * The two-column settings layout: a nav of section names that tracks the
 * scroll, beside a scrolling column of sections. Deep links (`#integrity`
 * from the command palette) scroll to their section on arrival.
 *
 * Settings and System both render inside this. It was the body of
 * SettingsPage until the installation-wide sections moved to their own page
 * — a second copy of the scroll-spy would have been the fifth anchored-
 * geometry copy all over again.
 *
 * The shared settings vocabulary (`settings-row`, `settings-btn`, …) is
 * loaded here too, because every panel that uses it renders inside this
 * shell on one page or the other.
 */
export function SettingsShell({
  sections,
  navLabel,
  navFooter,
  children,
}: {
  sections: VisibleSection[]
  navLabel: string
  /** A cross-link under the section list (Settings ↔ System). */
  navFooter?: ReactNode
  children: ReactNode
}) {
  const location = useLocation()
  // A deep link (`/system#data` from the palette or the budget picker) starts
  // highlighted; the scroll it triggers below hands the highlight to the
  // observer from there, so nothing sets state inside an effect.
  const [activeSection, setActiveSection] = useState<string>(
    () => location.hash.slice(1) || sections[0]?.id || ''
  )
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!location.hash) return
    document
      .getElementById(location.hash.slice(1))
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [location.hash])

  // Re-observe when the section list changes: budgetId gates several sections
  // and is_admin gates two (which arrive only after /auth/me resolves).
  const sectionKey = sections.map((s) => s.id).join(',')
  useEffect(() => {
    const contentEl = contentRef.current
    if (!contentEl) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible?.target.id) setActiveSection(visible.target.id)
      },
      { root: contentEl, rootMargin: '-20% 0px -60% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] }
    )
    for (const id of sectionKey.split(',')) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [sectionKey])

  function scrollToSection(id: string) {
    const el = document.getElementById(id)
    const contentEl = contentRef.current
    if (el && contentEl) {
      contentEl.scrollTo({ top: el.offsetTop - 20, behavior: 'smooth' })
      setActiveSection(id)
    }
  }

  return (
    <div className="settings-page">
      <nav className="settings-nav" aria-label={navLabel}>
        {sections.map(({ id, label, warn }) => (
          <button
            key={id}
            className={`settings-nav__link ${activeSection === id ? 'settings-nav__link--active' : ''}`}
            onClick={() => scrollToSection(id)}
            title={warn}
          >
            {label}
            {warn && (
              <>
                <span className="settings-nav__warn" aria-hidden />
                <span className="sr-only">{` — ${warn}`}</span>
              </>
            )}
          </button>
        ))}
        {navFooter && <div className="settings-nav__footer">{navFooter}</div>}
      </nav>

      <div className="settings-content" ref={contentRef}>
        {children}
      </div>
    </div>
  )
}
