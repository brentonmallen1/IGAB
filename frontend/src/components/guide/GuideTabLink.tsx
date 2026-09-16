import type { ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { GUIDE_TABS } from '../../stores/guideStore'
import { guideTabHref, type GuideLinkTarget } from '../../utils/guideLinks'
import './GuideTabLink.css'

/** "See How money counts" — a link to one Guide tab, labelled from the tab
 * list so a renamed tab cannot leave a stale link label behind. With an
 * `anchor` it lands on that section; `children` replace the label where the
 * section, not the tab, is what the reader is being sent to. */
export function GuideTabLink({
  tab,
  anchor,
  children,
}: GuideLinkTarget & { children?: ReactNode }) {
  const label = GUIDE_TABS.find((t) => t.id === tab)?.label ?? tab
  return (
    <Link to={guideTabHref(tab, anchor)} className="guide-tab-link">
      {children ?? `See ${label.charAt(0).toLowerCase() + label.slice(1)}`}
      <ArrowRight size={11} aria-hidden />
    </Link>
  )
}
