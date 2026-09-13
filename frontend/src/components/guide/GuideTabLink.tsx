import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { GUIDE_TABS, type GuideTab } from '../../stores/guideStore'
import './GuideTabLink.css'

/** "See How money counts" — a link to one Guide tab, labelled from the tab
 * list so a renamed tab cannot leave a stale link label behind. */
export function GuideTabLink({ tab }: { tab: GuideTab }) {
  const label = GUIDE_TABS.find((t) => t.id === tab)?.label ?? tab
  return (
    <Link to={`/guide?tab=${tab}`} className="guide-tab-link">
      See {label.charAt(0).toLowerCase() + label.slice(1)}
      <ArrowRight size={11} aria-hidden />
    </Link>
  )
}
